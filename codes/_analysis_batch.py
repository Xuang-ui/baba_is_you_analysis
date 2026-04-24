"""
批量分析器 - 读取行为链并输出完整的分析结果
参考 replay 模式实现，输出 DataFrame 格式
保留原CSV所有列，只对上下左右动作进行分析
使用 numpy 优化存储和转换性能
支持按地图分组的多进程并行
"""
import pandas as pd
import numpy as np
from codes.base_gameLogic import Action, GameOutcome
from codes._analyzer import Analysis, GridInfo
import os
from multiprocessing import Pool

class BatchAnalyzer:
    """批量分析行为链"""
    
    def __init__(self, csv_path='all_action_rt.csv', preload_maps=True):
        self.csv_path = csv_path
        # 定义所有可执行的动作
        self.action_map = {
            'Right': Action.right,
            'Down': Action.down,
            'Left': Action.left,
            'Up': Action.up,
            'Undo': Action.undo,
            'Restart': Action.restart,
            'Wait': Action.wait,
            'Quit': Action.quit,
        }
        # 移动类动作：需要完整分析
        self.movement_actions = {'Right', 'Down', 'Left', 'Up'}
        
        # 地图缓存
        self.map_cache = {}
        if preload_maps:
            self._preload_all_maps()
        
        # 预定义的分析列名（避免重复格式化字符串）
        self._analysis_columns = None
        self._original_columns = None
    
    def _preload_all_maps(self):
        """预加载所有游戏地图（缓存地图文本）"""
        map_names = ['intro', 'tutorial', 'base', 'target', 'break', 'helper', 'make', 'maze']
        print("📦 预加载地图中...")
        for map_name in map_names:
            try:
                filepath = f"../levels/{map_name}.txt"
                with open(filepath, 'r', encoding='utf-8') as f:
                    map_text = f.read().strip()
                # 缓存地图文本而不是 Analysis 对象
                self.map_cache[map_name] = map_text
            except FileNotFoundError:
                print(f"  ✗ {map_name} (文件不存在)")
            except Exception as e:
                print(f"  ✗ {map_name} (错误: {e})")
        print(f"✅ 预加载完成，共 {len(self.map_cache)} 个地图\n")
    
    def load_map(self, map_name):
        """加载地图（使用缓存的地图文本）"""
        map_text = None
        
        # 检查缓存
        if map_name in self.map_cache:
            # 从缓存中获取地图文本
            map_text = self.map_cache[map_name]
        else:
            # 缓存未命中，从文件读取
            try:
                filepath = f"../levels/{map_name}.txt"
                with open(filepath, 'r', encoding='utf-8') as f:
                    map_text = f.read().strip()
                # 缓存地图文本
                self.map_cache[map_name] = map_text
            except FileNotFoundError:
                print(f"警告: 地图文件不存在: {filepath}")
                return None
            except Exception as e:
                print(f"错误: 读取地图 {map_name} 失败: {e}")
                return None
        
        # 从文本创建新的 Analysis 对象（避免深拷贝问题）
        try:
            return Analysis.from_text(map_text)
        except Exception as e:
            print(f"错误: 解析地图 {map_name} 失败: {e}")
            return None
    
    def _initialize_columns(self, actions_df, sample_info):
        """初始化列名（只需执行一次）"""
        if self._original_columns is None:
            # 原始CSV的列
            self._original_columns = list(actions_df.columns)
            
            # 添加 Outcome 列
            self._all_columns = self._original_columns + ['Outcome']
            
            # 添加分析列
            analysis_cols = []
            for k in sample_info['pre'].keys():
                analysis_cols.append(f'pre_{k}')
            for k in sample_info['cha'].keys():
                analysis_cols.append(f'cha_{k}')
            for k in sample_info['inter'].keys():
                analysis_cols.append(f'inter_{k}')
            
            self._analysis_columns = analysis_cols
            self._all_columns.extend(analysis_cols)
            
            # 预计算分析列的索引位置
            self._outcome_idx = len(self._original_columns)
            self._analysis_start_idx = self._outcome_idx + 1
    
    def analyze_session(self, uid, map_name, actions_df):
        """分析单个会话的所有行动（numpy优化版）"""
        # 加载地图
        grid = self.load_map(map_name)
        if grid is None:
            return None
        
        # 确保 info observer 已加载
        if 'info' not in grid.observers:
            grid.add_observer('info')
        
        n_rows = len(actions_df)
        
        # 初始化列名（第一次执行时）
        if self._analysis_columns is None:
            # 执行一次移动动作获取 info 结构
            temp_grid = grid
            for _, row in actions_df.iterrows():
                if row['Action'] in self.movement_actions:
                    temp_grid, _, _ = temp_grid.step(self.action_map[row['Action']])
                    temp_info = temp_grid.get('info', 'info')
                    self._initialize_columns(actions_df, temp_info)
                    break
            # 重新加载地图
            grid = self.load_map(map_name)
            if 'info' not in grid.observers:
                grid.add_observer('info')
        
        # 确保列名一致性：重新排序以匹配原始列顺序
        if list(actions_df.columns) != self._original_columns:
            # 按照原始列顺序重新排列
            actions_df = actions_df[self._original_columns]
        
        # 转换为 numpy 数组（保留原始列）
        original_data = actions_df.values  # numpy array
        
        # 创建结果数组：原始列 + Outcome + 分析列
        n_original_cols = len(self._original_columns)
        n_total_cols = len(self._all_columns)
        result_data = np.empty((n_rows, n_total_cols), dtype=object)
        
        # 拷贝原始数据（确保列数正确）
        if original_data.shape[1] != n_original_cols:
            raise ValueError(f"列数不匹配！期望 {n_original_cols} 列，实际 {original_data.shape[1]} 列")
        
        result_data[:, :n_original_cols] = original_data
        
        # 获取 Action 列的索引
        action_col_idx = self._original_columns.index('Action')
        
        # 处理每一行
        for i in range(n_rows):
            action_name = original_data[i, action_col_idx]
            
            # 如果是可执行的动作
            if action_name in self.action_map:
                action = self.action_map[action_name]
                
                try:
                    # 执行动作
                    new_grid, outcome, basic_info = grid.step(action)
                    grid = new_grid
                    
                    # 添加 Outcome
                    result_data[i, n_original_cols] = outcome.name
                    
                    # 只对移动类动作进行详细分析
                    if action_name in self.movement_actions:
                        info = grid.get('info', 'info')
                        
                        # 一次性提取所有值（保持顺序）
                        all_values = (list(info['pre'].values()) + 
                                      list(info['cha'].values()) + 
                                      list(info['inter'].values()))
                        
                        # 验证值的数量
                        if len(all_values) != len(self._analysis_columns):
                            raise ValueError(f"分析值数量不匹配！期望 {len(self._analysis_columns)}, 实际 {len(all_values)}")
                        
                        # 批量切片赋值（117个值一次性赋值）
                        result_data[i, n_original_cols+1:] = all_values

                        
                except Exception as e:
                    print(f"错误: Uid={uid}, Map={map_name}, Action={action_name}: {e}")
                    result_data[i, n_original_cols] = 'Error'
        
        # 验证结果数组的维度
        expected_shape = (n_rows, len(self._all_columns))
        if result_data.shape != expected_shape:
            raise ValueError(f"结果数组维度错误！期望 {expected_shape}, 实际 {result_data.shape}")
        
        # 返回 numpy 数组（不转换为 DataFrame）
        return result_data
    
    def _analyze_all_singleprocess(self, grouped):
        """单进程分析所有会话"""
        result_arrays = []
        total = len(grouped)
        for idx, ((uid, map_name), group) in enumerate(grouped, 1):
            print(f"进度: {idx}/{total} - Uid={uid}, Map={map_name}")
            session_array = self.analyze_session(uid, map_name, group)
            if session_array is not None and len(session_array) > 0:
                result_arrays.append(session_array)
        return result_arrays
    
    def _analyze_all_multiprocess(self, grouped, n_processes=8):
        """多进程分析所有会话（按地图分组）"""
        # 按地图分组会话
        map_sessions = {}
        for (uid, map_name), group in grouped:
            if map_name not in map_sessions:
                map_sessions[map_name] = []
            map_sessions[map_name].append((uid, group))
        
        print(f"🔀 按地图分组: {len(map_sessions)} 个地图")
        
        actual_processes = min(n_processes, len(map_sessions))
        print(f"\n🚀 启动 {actual_processes} 个进程并行处理...\n")
        
        # 准备参数
        process_args = [(map_name, sessions) for map_name, sessions in map_sessions.items()]
        
        # 使用多进程处理（每个地图一个进程，最多n_processes个）
        with Pool(processes=actual_processes) as pool:
            # 使用 starmap 传递参数
            map_results = pool.starmap(self._process_map_sessions, process_args)
        
        # 过滤掉None，提取数组、列名和缓存统计
        result_arrays = []
        all_columns = None
        map_cache_stats = {}  # 存储每个地图的缓存统计
        
        for result in map_results:
            if result is not None:
                arr, cols, map_name, stats = result
                result_arrays.append(arr)
                map_cache_stats[map_name] = stats
                if all_columns is None:
                    all_columns = cols  # 保存列名
        
        # 保存列名到实例变量（用于后续转换）
        if all_columns is not None:
            self._all_columns = all_columns
        
        # 保存缓存统计（用于后续显示）
        self._map_cache_stats = map_cache_stats
        
        return result_arrays
    
    def _process_map_sessions(self, map_name, sessions):
        """处理单个地图的所有会话（用于多进程）"""
        from codes._analyzer import GridInfo
        
        print(f"📍 开始处理地图 {map_name}: {len(sessions)} 个会话")
        result_arrays = []
        
        for idx, (uid, group) in enumerate(sessions, 1):
            if idx % 10 == 0 or idx == len(sessions):
                print(f"  {map_name}: {idx}/{len(sessions)}")
            session_array = self.analyze_session(uid, map_name, group)
            if session_array is not None and len(session_array) > 0:
                result_arrays.append(session_array)
        
        if result_arrays:
            # 合并该地图的所有会话
            combined = np.vstack(result_arrays)
            
            # 获取该进程的缓存统计
            cache_stats = GridInfo.get_cache_stats()
            
            print(f"✅ 地图 {map_name} 完成: {len(combined)} 行, 列数 {combined.shape[1]}")
            
            # 验证列数
            expected_cols = len(self._all_columns)
            actual_cols = combined.shape[1]
            if actual_cols != expected_cols:
                print(f"⚠️  警告：{map_name} 列数不匹配！期望 {expected_cols}, 实际 {actual_cols}")
            
            # 返回数据、列名和缓存统计
            return (combined, self._all_columns, map_name, cache_stats)
        return None
    
    def analyze_all(self, limit=None, output_file='analysis_results.csv', clear_cache=True, use_multiprocess=False, n_processes=8):
        """分析所有会话（支持多进程）"""
        from recorder import State
        from codes._analyzer import GridInfo
        
        # 清空之前的缓存
        if clear_cache:
            GridInfo.clear_cache()
        
        # 读取 CSV（读取所有列）
        print(f"📖 读取 CSV 文件: {self.csv_path}")
        df = pd.read_csv(self.csv_path)
        
        print(f"原始数据: {len(df)} 行")
        
        # 过滤掉必要字段缺失的行
        df = df.query('Uid != -1 and Level != -1')
        print(f"清洗后数据: {len(df)} 行")
        
        # 按 (Uid, Map) 分组
        grouped = list(df.groupby(['Uid', 'Map'], sort=False))
        
        print(f"总共 {len(grouped)} 个会话\n")
        
        if limit:
            print(f"⚠️  限制分析前 {limit} 个会话\n")
            grouped = grouped[:limit]
        
        # 根据是否使用多进程选择处理方式
        if use_multiprocess:
            result_arrays = self._analyze_all_multiprocess(grouped, n_processes)
        else:
            result_arrays = self._analyze_all_singleprocess(grouped)
        
        # 合并所有 numpy 数组，然后一次性转换为 DataFrame
        if result_arrays:
            # 使用 numpy 的 vstack 批量合并（比 concat 快）
            combined_array = np.vstack(result_arrays)
            
            # 一次性转换为 DataFrame
            result_df = pd.DataFrame(combined_array, columns=self._all_columns)
            
            # 打印缓存统计
            if use_multiprocess and hasattr(self, '_map_cache_stats'):
                # 多进程模式：显示每个地图的缓存统计
                print(f"\n{'='*60}")
                print(f"📊 各地图缓存统计 (多进程):")
                
                total_hits = 0
                total_misses = 0
                total_cache_size = 0
                
                for map_name, stats in self._map_cache_stats.items():
                    print(f"\n  🗺️  {map_name}:")
                    print(f"     命中: {stats['hits']:,}, 未命中: {stats['misses']:,}")
                    print(f"     命中率: {stats['hit_rate']}, 缓存: {stats['cache_size']:,} 个状态")
                    total_hits += stats['hits']
                    total_misses += stats['misses']
                    total_cache_size += stats['cache_size']
                
                total = total_hits + total_misses
                overall_hit_rate = total_hits / total * 100 if total > 0 else 0
                
                print(f"\n  📊 汇总:")
                print(f"     总命中: {total_hits:,}, 总未命中: {total_misses:,}")
                print(f"     总命中率: {overall_hit_rate:.2f}%")
                print(f"     总缓存: {total_cache_size:,} 个唯一状态")
                print(f"{'='*60}")
            else:
                # 单进程模式：显示GridInfo的缓存统计
                state_stats = GridInfo.get_cache_stats()
                
                print(f"\n{'='*60}")
                print(f"📊 状态缓存统计 (GridInfo):")
                print(f"  缓存命中次数: {state_stats['hits']:,}")
                print(f"  缓存未命中次数: {state_stats['misses']:,}")
                print(f"  总查询次数: {state_stats['total']:,}")
                print(f"  命中率: {state_stats['hit_rate']}")
                print(f"  缓存大小: {state_stats['cache_size']:,} 个唯一状态")
                print(f"{'='*60}")
            
            # 保存到文件
            result_df.to_csv(output_file, index=False)
            print(f"\n✅ 分析完成! 结果已保存到: {output_file}")
            print(f"总共分析了 {len(result_df):,} 个行动步骤")
            print(f"分析列数: {len(result_df.columns)}")
            
            return result_df
        else:
            print("❌ 没有成功分析的会话")
            return None
    
    def analyze_single(self, uid, map_name, output_file=None):
        """分析单个会话"""
        print(f"分析会话: Uid={uid}, Map={map_name}")
        
        # 读取该会话的数据（读取所有列）
        df = pd.read_csv(self.csv_path)
        df = df.dropna(subset=['Uid', 'Action', 'Map'])
        
        # 过滤出目标会话
        session_df = df[(df['Uid'] == uid) & (df['Map'] == map_name)]
        
        if session_df.empty:
            print(f"未找到匹配的会话: Uid={uid}, Map={map_name}")
            return None
        
        print(f"找到 {len(session_df)} 个行动")
        
        # 分析会话（返回 numpy 数组）
        result_array = self.analyze_session(uid, map_name, session_df)
        
        if result_array is not None and len(result_array) > 0:
            # 转换为 DataFrame
            result_df = pd.DataFrame(result_array, columns=self._all_columns)
            
            if output_file:
                result_df.to_csv(output_file, index=False)
                print(f"结果已保存到: {output_file}")
            
            print(f"\n分析完成! 共 {len(result_df)} 个步骤")
            print(f"列数: {len(result_df.columns)}")
            print(f"\n结果预览:")
            print(result_df.head(10))
            
            return result_df
        else:
            print("分析失败")
            return None


def main():
    """主函数 - 示例用法"""
    print("="*80)
    print("🎮 BABA IS YOU - 批量分析器")
    print("="*80)
    print()
    
    analyzer = BatchAnalyzer()
    
    # 示例1: 分析单个会话
    print("=" * 80)
    print("示例1: 分析单个会话")
    print("=" * 80)
    df = analyzer.analyze_single(uid=110, map_name='intro', 
                                   output_file='single_session_analysis.csv')
    
    # 示例2: 分析前5个会话
    # print("=" * 80)
    # print("示例2: 批量分析前5个会话")
    # print("=" * 80)
    # df = analyzer.analyze_all(limit=5, output_file='batch_analysis_sample.csv')
    
    # 示例3: 分析所有会话（警告：可能需要很长时间）
    # print("=" * 80)
    # print("示例3: 分析所有会话")
    # print("=" * 80)
    # df = analyzer.analyze_all(output_file='all_sessions_analysis.csv')


if __name__ == "__main__":
    main()