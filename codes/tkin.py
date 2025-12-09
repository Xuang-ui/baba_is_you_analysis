import tkinter as tk
from tkinter import ttk, messagebox, simpledialog, filedialog
import tkinter.font as tkFont
from PIL import Image, ImageTk
import os
import sys
import ctypes
import pandas as pd
from recorder import Gridmap
from plan_evaluator import PlanValueEvaluator
from codes.base_gameLogic import Action, GameOutcome
from codes.base_rule import RuleManager, entity_id_to_texture
from codes._solver import interaction
from codes.base_entity import Entity
from codes._analyzer import Analysis

def pad_status(text, width=30):
    """
    计算文本显示宽度并用空格填充到指定宽度
    中文、全角字符算2个单位，ASCII算1个单位，emoji算2个单位
    """
    # lines = text.split('\n')
    # padded_lines = []
    # for line in lines:
    #     display_width = 0
    #     for char in line:
    #         # 中文字符、全角字符范围
    #         if '\u4e00' <= char <= '\u9fff' or '\u3000' <= char <= '\u303f' or '\uff00' <= char <= '\uffef':
    #             display_width += 2
    #         # emoji 通常在这些范围
    #         elif '\U0001f300' <= char <= '\U0001f9ff' or '\u2600' <= char <= '\u26ff':
    #             display_width += 2
    #         else:
    #             display_width += 1
    #     padding = max(0, width - display_width)
    #     padded_lines.append(line + ' ' * padding)
    # return '\n'.join(padded_lines)
    return text

def code_to_str(code):
    """将下划线分隔的代码转换为可读字符串"""
    return ' '.join(code.split('_')[1:])

def format_info_dict(info_dict):
    """格式化信息字典，合并相似的项目"""
    if not info_dict:
        return "无信息"
    
    result = []
    processed_keys = set()
    standalone_items = []
    
    # 先处理所有未匹配的 bool 变量（放在最前面）
    known_patterns = [
        'bool_man_exist_', 'bool_man_reachable_', 'bool_man_unreachable_', 
        'bool_man_approach_', 'bool_man_avoid_',
        'bool_game_reach_', 'bool_game_reachable_', 'bool_game_unreachable_',
        'bool_game_approach_', 'bool_game_avoid_',
        'bool_has_', 'bool_form_', 'bool_break_',
        'bool_direct_', 'bool_indirect_'
    ]
    
    for code, value in info_dict.items():
        if isinstance(value, bool) and value:
            # 检查是否匹配已知模式
            is_known = any(code.startswith(pattern) for pattern in known_patterns)
            if not is_known:
                standalone_items.append(code_to_str(code))
                processed_keys.add(code)
                result.append(code_to_str(code))
    
    # 现在处理特殊格式
    # 5. 处理其他模式
    other_patterns = [
        ('bool_has_', '_rule', 'rule'),
        ('bool_form_', '_rule', 'form rule'),
        ('bool_break_', '_rule', 'break rule'),
        ('bool_direct_', '_inter', 'direct inter'),
        ('bool_indirect_', '_inter', 'indirect inter'),
    ]
    
    for prefix, suffix, display_name in other_patterns:
        matched_values = []
        for code, value in info_dict.items():
            if code in processed_keys:
                continue
            if isinstance(value, bool) and value and code.startswith(prefix) and code.endswith(suffix):
                prop_name = code[len(prefix):-len(suffix)]
                if prop_name and '_' not in prop_name:
                    matched_values.append(prop_name)
                    processed_keys.add(code)
        
        if matched_values:
            result.append(f"{display_name}: {','.join(sorted(matched_values))}")
   
    # 1. exist 行：bool_man_exist_{prop}_object + 距离 num_man_{prop}_object
    exist_items = []
    for code, value in info_dict.items():
        if isinstance(value, bool) and value and code.startswith('bool_man_exist_') and code.endswith('_object'):
            prop_name = code[15:-7]
            if prop_name and '_' not in prop_name:
                processed_keys.add(code)
                dist_key = f"num_man_{prop_name}_object"
                dist = info_dict.get(dist_key)
                if dist is not None and dist != float('inf'):
                    exist_items.append(f"{prop_name}({dist})")
                else:
                    exist_items.append(prop_name)
    if exist_items:
        result.append(f"exist: {', '.join(sorted(exist_items))}")
    
    # 2. reach 行：num_game_{prop}_object（排除inf）
    reach_items = []
    for code, value in info_dict.items():
        if code.startswith('num_game_') and code.endswith('_object'):
            if value is not None and value != float('inf'):
                prop_name = code[9:-7]
                if prop_name and '_' not in prop_name:
                    reach_items.append(f"{prop_name}({value})")
    if reach_items:
        result.append(f"reach: {', '.join(sorted(reach_items, key=lambda x: x.split('(')[0]))}")
    
    # 3. direct 行：合并 approach, avoid, reachable(√), unreachable(×)
    direct_items = []
    man_props = set()
    
    # 收集所有相关的 prop
    for code, value in info_dict.items():
        if isinstance(value, bool) and value:
            if any(code.startswith(p) for p in ['bool_man_approach_', 'bool_man_avoid_', 'bool_man_reachable_', 'bool_man_unreachable_']):
                if code.endswith('_object'):
                    if code.startswith('bool_man_approach_'):
                        prop_name = code[18:-7]
                    elif code.startswith('bool_man_avoid_'):
                        prop_name = code[15:-7]
                    elif code.startswith('bool_man_reachable_'):
                        prop_name = code[19:-7]
                    elif code.startswith('bool_man_unreachable_'):
                        prop_name = code[21:-7]
                    else:
                        continue
                    
                    if prop_name and '_' not in prop_name:
                        man_props.add(prop_name)
                        processed_keys.add(code)
    
    for prop in sorted(man_props):
        tags = []

        if info_dict.get(f'bool_man_reachable_{prop}_object', False):
            tags.append('√')
        elif info_dict.get(f'bool_man_unreachable_{prop}_object', False):
            tags.append('×')
        elif info_dict.get(f'bool_man_approach_{prop}_object', False):
            tags.append('+')
        elif info_dict.get(f'bool_man_avoid_{prop}_object', False):
            tags.append('-')
        
        if tags:
            direct_items.append(f"{prop}({''.join(tags)})")
    
    if direct_items:
        result.append(f"direct: {', '.join(sorted(direct_items, key=lambda x: x.split('(')[0]))}")
    
    # 4. indirect 行：合并 approach, avoid, reachable(√), unreachable(×)
    indirect_items = []
    game_props = set()
    
    for code, value in info_dict.items():
        if isinstance(value, bool) and value:
            if any(code.startswith(p) for p in ['bool_game_approach_', 'bool_game_avoid_', 'bool_game_reachable_', 'bool_game_unreachable_']):
                if code.endswith('_object'):
                    if code.startswith('bool_game_approach_'):
                        prop_name = code[19:-7]
                    elif code.startswith('bool_game_avoid_'):
                        prop_name = code[16:-7]
                    elif code.startswith('bool_game_reachable_'):
                        prop_name = code[20:-7]
                    elif code.startswith('bool_game_unreachable_'):
                        prop_name = code[22:-7]
                    else:
                        continue
                    
                    if prop_name and '_' not in prop_name:
                        game_props.add(prop_name)
                        processed_keys.add(code)
    
    for prop in sorted(game_props):
        tags = []

        if info_dict.get(f'bool_game_reachable_{prop}_object', False):
            tags.append('√')
        elif info_dict.get(f'bool_game_unreachable_{prop}_object', False):
            tags.append('×')
        elif info_dict.get(f'bool_game_approach_{prop}_object', False):
            tags.append('+')
        elif info_dict.get(f'bool_game_avoid_{prop}_object', False):
            tags.append('-')
        
        if tags:
            indirect_items.append(f"{prop}({''.join(tags)})")
    
    if indirect_items:
        result.append(f"indirect: {', '.join(sorted(indirect_items, key=lambda x: x.split('(')[0]))}")
    
 

    
    return '\n'.join(result) if result else "无"

class GameMode:
    """游戏模式"""
    def __init__(self, parent):
        self.parent = parent
        self.grid = None
        self.game_state = GameOutcome.Continue
        self.step_count = 0
    
    def set_grid(self, grid):
        """设置网格"""
        self.grid = grid
    
    def step(self, action):
        """执行游戏步骤"""
        if self.grid:
            new_grid, self.game_state, _ = self.grid.step(action)
            self.grid = new_grid  # 更新grid引用
            self.step_count += 1
    
    def get_status(self):
        """获取游戏状态"""
        DICT = {
            GameOutcome.Win: "🎉 胜利",
            GameOutcome.Defeat: "💀 失败",
            GameOutcome.Still: "⏸️ 请撤销或重启",
            GameOutcome.Quit: "👋 退出",
            GameOutcome.Continue: "🎯 进行中"
        }
        return pad_status(DICT[self.game_state])

class AnalysisMode:
    """分析模式"""
    def __init__(self, parent):
        self.parent = parent
        self.grid = None
        self.selected_com = None
        self.highlighted_coms = set()
        self.highlighted_paths = set()
        self.status = None

    def set_grid(self, grid):
        """设置网格"""
        self.grid = grid
        if self.grid:
            self.grid.add_observer('com')
        self.clear_selection()
    
    def clear_selection(self):
        """清除选择"""
        self.selected_com = None
        self.status = None
        self.highlighted_coms.clear()
        self.highlighted_paths.clear()
    
    def select_community(self, coord):
        """选择社区"""
        if not self.grid or 'com' not in self.grid.observers:
            return
        # 
        tile = self.grid.get_tile(coord)
        cg = self.grid.get_observer('com')
        clicked_com = cg.get_community(tile)
        
        if clicked_com:
            
            if self.selected_com is None or self.selected_com.id == clicked_com.id:
                # 第一次点击：高亮显示社区
                self.selected_com = clicked_com
                self.highlighted_coms = {clicked_com.id}
                self.highlighted_paths.clear()
                self.status = f"选中起始社区\n {clicked_com.get_description()}\n再次点击选择终点"
            
            else:
                # 第二次点击：高亮显示路径
                self.highlighted_coms.add(clicked_com.id)
                try:
                    paths = self.grid.get('com', 'path')
                    all_path = paths[self.selected_com.id][clicked_com.id]
                    for path in all_path:
                        for idx in path:
                            self.highlighted_paths.add(idx)
                    self.status = interaction(self.selected_com.example, clicked_com.example, self.grid)
                    self.selected_com = None
                except Exception as e:
                    self.status = f"路径获取错误: {e}"

        else:
            self.status = f"点击坐标 {coord} 没有找到社区"
    
    def get_status(self):
        """获取分析状态"""
        if self.status is None:
            return pad_status("社区分析模式\n点击格子查看社区")
        return pad_status(self.status)

class EditMode:
    """编辑模式"""
    def __init__(self, parent):
        self.parent = parent
        self.grid = None
        self.selected_coord = None
        self.editing_entity = None
        self.status = None
        
    def set_grid(self, grid):
        """设置网格"""
        self.grid = grid
        
    def select_coord(self, coord):
        """选择坐标进行编辑"""
        self.selected_coord = coord
        self.status = f"选中坐标 {coord}\n按键盘输入实体ID\n空格清空"
    
    def add_entity(self, entity_id):
        """添加实体到选中坐标"""
        if self.selected_coord and self.grid:
            # 清空当前坐标的所有实体
            tile = self.grid.get_tile(self.selected_coord)
            entity = Entity(entity_id, self.selected_coord)
            tile.add_entity(entity)         
            self.status = f"在 {self.selected_coord} 添加\n实体 '{entity.get_full_name()}'"
            return 
        return "请先选择坐标"
    
    def clear_coord(self):
        """清空选中坐标"""
        if self.selected_coord and self.grid:
            tile = self.grid.get_tile(self.selected_coord)
            tile.clear_entities()
            self.status = f"清空坐标 {self.selected_coord}"
            return 
        return "请先选择坐标"
    
    def move_selection(self, direction):
        """移动选中坐标"""
        if not self.selected_coord or not self.grid:
            self.status = "请先选择坐标"   
            return 
        
        x, y = self.selected_coord
        new_x, new_y = x, y
        
        if direction == 'up':
            new_y = min(y + 1, self.grid.height - 1)
        elif direction == 'down':
            new_y = max(y - 1, 0)
        elif direction == 'left':
            new_x = max(x - 1, 0)
        elif direction == 'right':
            new_x = min(x + 1, self.grid.width - 1)
        
        self.selected_coord = (new_x, new_y)
        self.status = f"移动到坐标 {self.selected_coord}"
        return 
    
    def get_status(self):
        """获取编辑状态"""
        if self.status is None:
            return pad_status("编辑模式\n请选择坐标")
        return pad_status(self.status)

class ReplayMode:
    """回放模式"""
    # 类级别缓存：所有实例共享
    _cached = {}
    _data_loaded = False

    def __init__(self, parent):
        self.parent = parent
        self.grid = None
        self.actions = []
        self.times = []
        self.step_count = 0
        self.running = False
        self.game_state = GameOutcome.Continue
        # 确保类级缓存已加载
        self.__class__.preload_data()

    def set_grid(self, grid):
        self.grid = grid
        self.parent.update_display()

    def load_actions(self, uid, map_name):
        """根据uid和map从缓存获取动作与时间序列"""
        try:
            # 确保已加载缓存（类级）
            cls = self.__class__
            if not cls._data_loaded:
                cls.preload_data()
            key = (int(uid), str(map_name))
            record = cls._cached.get(key)
            if not record:
                return [], []
            raw_actions = record.get('Action', [])
            times = record.get('Before', [])
            legal_action = {
                'Right': Action.right,
                'Down': Action.down,
                'Left': Action.left,
                'Up': Action.up,
                'Undo': Action.undo,
                'Restart': Action.restart,
                'Wait': Action.wait,
                'Quit': Action.quit,
            }
            actions = [legal_action[a] for a in raw_actions if a in legal_action]
            # 与动作保持相同长度：过滤掉非法动作对应的时间
            filtered_times = []
            for a, t in zip(raw_actions, times):
                if a in legal_action:
                    filtered_times.append(t)
            return actions, filtered_times
        except Exception as e:
            messagebox.showerror("回放失败", f"读取缓存失败: {e}")
            return [], []

    @classmethod
    def preload_data(cls):
        """一次性读取CSV并构建 (Uid, Map) 到 序列 的缓存"""
        try:
            df = pd.read_csv('all_action_rt.csv', usecols=['Uid', 'Map', 'Action', 'Before'])
            # 清洗：丢弃缺失Uid/Action的行
            df = df.dropna(subset=['Uid', 'Action'])
            # 统一类型
            df['Uid'] = pd.to_numeric(df['Uid'], errors='coerce').astype('Int64')
            df['Map'] = df['Map'].astype(str).fillna('')
            # 只保留需要的列顺序
            df = df[['Uid', 'Map', 'Action', 'Before']]
            # 分组缓存
            cls._cached.clear()
            for (uid, map_name), group in df.groupby(['Uid', 'Map'], sort=False):
                actions = group['Action'].astype(str).tolist()
                times = group['Before'].tolist()
                cls._cached[(int(uid), str(map_name))] = {
                    'Action': actions,
                    'Before': times,
                }
            cls._data_loaded = True
        except Exception as e:
            # 读取失败不打断流程；实际使用时再报错
            cls._data_loaded = False

    def start(self, actions, times):
        self.actions = actions
        self.times = times
        self.running = True
        self.step_count = 0
        self.game_state = GameOutcome.Continue
        self._wait_then_step()

    def _schedule_next(self):
        """兼容旧调用，改为等待后再执行一步"""
        self._wait_then_step()

    def _wait_then_step(self):
        if not self.running:
            return
        if self.step_count >= len(self.actions):
            self.running = False
            messagebox.showinfo("回放结束", "动作序列已播放完毕")
            return
        # 先等待本步的时间，再执行动作
        wait_time = self.times[self.step_count]
        self.parent.root.after(int(wait_time * 500), self._do_step)

    def _do_step(self):
        if not self.running:
            return
        if self.step_count >= len(self.actions):
            self.running = False
            messagebox.showinfo("回放结束", "动作序列已播放完毕")
            return
        action = self.actions[self.step_count]
        if self.grid:
            new_grid, self.game_state, _ = self.grid.step(action)
            self.grid = new_grid
            self.parent.grid = new_grid
            self.parent.game_mode.step_count += 1
            self.parent.update_display()
        self.step_count += 1
        # 本步执行后，进入下一步的等待
        self._wait_then_step()

    def stop(self):
        self.running = False

    def get_status(self):
        DICT = {
            GameOutcome.Win: "🎉 胜利",
            GameOutcome.Defeat: "💀 失败",
            GameOutcome.Still: "⏸️ 请撤销或重启",
            GameOutcome.Quit: "👋 退出",
            GameOutcome.Continue: "🎯 进行中"
        }
        return pad_status(DICT[self.game_state])
class TkinterGame:
    """基于tkinter的BABA IS YOU游戏"""
    def __init__(self, map_text=None):
        """初始化游戏"""
        self.map_text = map_text or self.get_default_map()
        
        # 贴图缓存和路径
        self.texture_cache = {}
        self.texture_path = os.path.join(os.path.dirname(__file__), 'textures')
        
        # 创建主窗口
        self.root = tk.Tk()
        self.root.title("🎮 BABA IS YOU - 图形界面版")
        self.root.geometry("1400x900")
        self.root.resizable(True, True)
        
        # 设置样式
        self.setup_styles()
        
        # 创建模式
        self.game_mode = GameMode(self)
        self.analysis_mode = AnalysisMode(self)
        self.edit_mode = EditMode(self)
        self.replay_mode = ReplayMode(self)
        self.current_mode = "game"  # "game"、"analysis"、"edit"、"replay"
        
        # 创建界面
        self.create_widgets()
        # 绑定键盘事件
        self.bind_events()
        
        # 初始化网格
        self.load_grid()
        
        # 更新显示
        self.layout = None
        self.update_display()

    def open_action_space(self):
        """按钮回调：调用 grid.describe_action_space() 并在交互窗口中展示归一化表格（norm）。"""
        if not getattr(self, 'grid', None):
            messagebox.showwarning('无地图', '当前未加载任何地图')
            return
        try:
            self.grid.expand()
            raw, norm = self.grid.evaluate()
        except Exception as e:
            messagebox.showerror('错误', f'获取动作空间失败: {e}')
            return
        if norm is None or norm.empty:
            messagebox.showinfo('无动作', '当前地图未检测到动作样本')
            return
        title = f"动作空间 - {getattr(self, 'map_text', '')[:20]}"
        self.show_dataframe_window(norm, title)

    def open_action_space_raw(self):
        """显示 raw 表格（原始特征）。"""
        if not getattr(self, 'grid', None):
            messagebox.showwarning('无地图', '当前未加载任何地图')
            return
        try:
            self.grid.expand()
            raw, norm = self.grid.evaluate()
        except Exception as e:
            messagebox.showerror('错误', f'获取动作空间失败: {e}')
            return
        if raw is None or raw.empty:
            messagebox.showinfo('无动作', '当前地图未检测到动作样本')
            return
        title = f"动作空间 (raw) - {getattr(self, 'map_text', '')[:20]}"
        self.show_dataframe_window(raw, title)

    def open_action_space_norm(self):
        """显示 norm 表格（归一化排名）。"""
        if not getattr(self, 'grid', None):
            messagebox.showwarning('无地图', '当前未加载任何地图')
            return
        try:
            self.grid.expand()
            raw, norm = self.grid.evaluate()
        except Exception as e:
            messagebox.showerror('错误', f'获取动作空间失败: {e}')
            return
        if norm is None or norm.empty:
            messagebox.showinfo('无动作', '当前地图未检测到动作样本')
            return
        title = f"动作空间 (norm) - {getattr(self, 'map_text', '')[:20]}"
        self.show_dataframe_window(norm, title)

    def show_dataframe_window(self, df, title='DataFrame'):
        """在一个可排序/过滤的 Toplevel 中展示 pandas DataFrame。

        - 支持点击表头排序
        - 支持在顶部输入框按行索引或任意列做简单包含过滤
        """
        win = tk.Toplevel(self.root)
        win.title(title)
        win.geometry('900x600')

        # 顶部搜索栏
        top_frame = ttk.Frame(win)
        top_frame.pack(fill=tk.X, padx=6, pady=6)

        ttk.Label(top_frame, text='Filter:').pack(side=tk.LEFT)
        filter_var = tk.StringVar()
        filter_entry = ttk.Entry(top_frame, textvariable=filter_var)
        filter_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(6, 6))

        def apply_filter(*args):
            q = filter_var.get().strip().lower()
            if q == '':
                rows = df
            else:
                # 如果 q 出现在 index 或任一列的字符串形式中，则保留该行
                mask = df.index.to_series().astype(str).str.lower().str.contains(q)
                for c in df.columns:
                    try:
                        mask = mask | df[c].astype(str).str.lower().str.contains(q)
                    except Exception:
                        pass
                rows = df[mask]
            populate_tree(rows)

        filter_var.trace_add('write', apply_filter)

        # Treeview 区域
        frame = ttk.Frame(win)
        frame.pack(fill=tk.BOTH, expand=True, padx=6, pady=(0,6))

        cols = list(df.columns)
        tree = ttk.Treeview(frame, columns=['_index'] + cols, show='headings')

        # 垂直与水平滚动条
        vsb = ttk.Scrollbar(frame, orient='vertical', command=tree.yview)
        hsb = ttk.Scrollbar(frame, orient='horizontal', command=tree.xview)
        tree.configure(yscroll=vsb.set, xscroll=hsb.set)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        hsb.pack(side=tk.BOTTOM, fill=tk.X)
        tree.pack(fill=tk.BOTH, expand=True)

        # 设置表头
        tree.heading('_index', text='id')
        tree.column('_index', width=180, anchor=tk.W)
        tree['displaycolumns'] = ['_index'] + cols
        for c in cols:
            tree.heading(c, text=c)
            tree.column(c, width=120, anchor=tk.CENTER)

        # mapping from tree iid -> original df index value
        iid_to_idx = {}

        def populate_tree(subdf):
            # 清空
            for r in tree.get_children():
                tree.delete(r)
            iid_to_idx.clear()
            # 转换为字符串并插入（显示 id 为第一个 '_' 之后的部分）
            for i, (idx, row) in enumerate(subdf.iterrows()):
                raw_idx_str = str(idx)
                display_id = raw_idx_str.split('_', 1)[1] if '_' in raw_idx_str else raw_idx_str
                iid = f'row{i}'
                iid_to_idx[iid] = idx
                values = [display_id] + [self._format_cell(row[c]) for c in cols]
                tree.insert('', tk.END, iid=iid, values=values)

        # 支持列排序
        sort_states = {}
        def sort_by(col):
            asc = sort_states.get(col, True)
            try:
                sorted_df = df.sort_values(by=col, ascending=asc, na_position='last')
            except Exception:
                # 非数字或无法直接排序，按字符串排序
                sorted_df = df.reindex(sorted(df.index, key=lambda x: str(df.loc[x, col]) if col in df.columns else str(x)), copy=False)
            sort_states[col] = not asc
            populate_tree(sorted_df)

        # 绑定点击表头进行排序
        def on_heading_click(event):
            region = tree.identify_region(event.x, event.y)
            if region == 'heading':
                col = tree.identify_column(event.x)
                # col 格式 '#1', '#2'... 映射到 displaycolumns
                try:
                    idx = int(col.replace('#', '')) - 1
                    disp = tree['displaycolumns'][idx]
                    if disp == '_index':
                        # 排序索引
                        sorted_df = df.sort_index(ascending=not sort_states.get('_index', False))
                        sort_states['_index'] = not sort_states.get('_index', False)
                        populate_tree(sorted_df)
                        return
                    sort_by(disp)
                except Exception:
                    return

        tree.bind('<Button-1>', on_heading_click, add='+')

        # 初始填充
        populate_tree(df)

        # 双击行可以弹出详细信息
        def on_double_click(event):
            item = tree.identify_row(event.y)
            if not item:
                return
            orig_idx = iid_to_idx.get(item)
            if orig_idx is None:
                return
            try:
                detail = df.loc[orig_idx].to_frame().to_string()
            except Exception:
                detail = str(orig_idx)
            detail_win = tk.Toplevel(win)
            detail_win.title(f'Detail - {orig_idx}')
            txt = tk.Text(detail_win, wrap=tk.NONE)
            txt.insert('1.0', detail)
            txt.pack(fill=tk.BOTH, expand=True)

        tree.bind('<Double-1>', on_double_click)

    def _format_cell(self, v, maxlen=50):
        """格式化单元格显示：
        - 数值（int/float/np.number）保留 3 位小数（整数不显示小数点）
        - 其他类型转为字符串，超长则截断为 maxlen
        """
        try:
            # 避免导入 numpy explicitly; isinstance against numbers.Number handles np numbers too
            import numbers
            if isinstance(v, numbers.Number):
                # 对于浮点数保留 3 位小数；对于整数不显示小数点
                if isinstance(v, float):
                    if v == float('inf') or v == float('-inf') or v != v:
                        return str(v)
                    return f"{v:.3f}"
                else:
                    # 整数类型
                    return str(int(v))
        except Exception:
            pass
        s = str(v)
        if len(s) > maxlen:
            return s[:maxlen-3] + '...'
        return s
        
    def get_default_map(self):
            """获取默认地图"""
            return '''
        .........
        .B02.....
        .S03.....
        ......b..
        ..s......'''
    
    def setup_styles(self):
        """设置样式"""
        self.colors = {
            'background': '#2b2b2b',
            'text': '#ffffff',
            'coordinate': '#888888',
            'grid': '#444444'
        }
        
        # 字体设置
        self.font_large = tkFont.Font(family="Arial", size=14, weight="bold")
        self.font_medium = tkFont.Font(family="Arial", size=12)
        self.font_small = tkFont.Font(family="Arial", size=10)
        
        # 按钮样式
        style = ttk.Style()
        style.configure('Game.TButton', font=self.font_medium)
    
    def create_widgets(self):
        """创建界面组件"""
        # 主容器
        main_frame = ttk.Frame(self.root)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # 创建三个自适应面板
        self.create_control_panel(main_frame)
        self.create_game_area(main_frame)
        self.create_info_panel(main_frame)
        
        # 配置grid权重，让面板按比例自适应（2:5:3）
        main_frame.grid_columnconfigure(0, weight=0, minsize=200)  # 控制面板（固定宽度）
        main_frame.grid_columnconfigure(1, weight=4)    # 游戏区域（主要区域）
        main_frame.grid_columnconfigure(2, weight=0, minsize=200)   # 信息面板（固定宽度）
        main_frame.grid_rowconfigure(0, weight=1)
    
    def create_control_panel(self, parent):
        """创建控制面板（固定宽度）"""
        control_frame = ttk.LabelFrame(parent, text="🎮 控制面板", padding="10")
        control_frame.grid(row=0, column=0, sticky=(tk.E,tk.W, tk.N, tk.S), padx=(10, 0))

        # 模式切换
        mode_frame = ttk.LabelFrame(control_frame, text="模式选择", padding="5")
        mode_frame.pack(fill=tk.X, pady=(0, 10))

        self.mode_var = tk.StringVar(value="game")
        ttk.Radiobutton(mode_frame, text="游戏模式", variable=self.mode_var,
                       value="game", command=self.switch_mode, takefocus=0).pack(anchor=tk.W)
        ttk.Radiobutton(mode_frame, text="分析模式", variable=self.mode_var,
                       value="analysis", command=self.switch_mode, takefocus=0).pack(anchor=tk.W)
        ttk.Radiobutton(mode_frame, text="编辑模式", variable=self.mode_var,
                       value="edit", command=self.switch_mode, takefocus=0).pack(anchor=tk.W)
        ttk.Radiobutton(mode_frame, text="回放模式", variable=self.mode_var,
                       value="replay", command=self.switch_mode, takefocus=0).pack(anchor=tk.W)

        # 地图选择
        map_frame = ttk.LabelFrame(control_frame, text="地图选择", padding="5")
        map_frame.pack(fill=tk.X, pady=(0, 10))

        ttk.Button(map_frame, text="intro", command=self.load_intro_map,
                  style='Game.TButton', takefocus=0).pack(fill=tk.X, pady=2)
        ttk.Button(map_frame, text="tutorial", command=self.load_tutorial_map,
                  style='Game.TButton', takefocus=0).pack(fill=tk.X, pady=2)
        ttk.Button(map_frame, text="base", command=self.load_base_map,
                  style='Game.TButton', takefocus=0).pack(fill=tk.X, pady=2)
        ttk.Button(map_frame, text="target", command=self.load_target_map,
                  style='Game.TButton', takefocus=0).pack(fill=tk.X, pady=2)
        ttk.Button(map_frame, text="选择地图", command=self.load_selected_map,
                  style='Game.TButton', takefocus=0).pack(fill=tk.X, pady=2)
        ttk.Button(map_frame, text="新建地图", command=self.create_empty_map,
                  style='Game.TButton', takefocus=0).pack(fill=tk.X, pady=2)
        ttk.Button(map_frame, text="保存地图", command=self.save_map,
                  style='Game.TButton', takefocus=0).pack(fill=tk.X, pady=2)

        # 打开动作空间表格（原始/归一化视图）——两个按钮分别显示 raw / norm
        btn_frame = ttk.Frame(map_frame)
        btn_frame.pack(fill=tk.X, pady=2)
        ttk.Button(btn_frame, text="动作空间 (raw)", command=self.open_action_space_raw,
                  style='Game.TButton', takefocus=0).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0,4))
        ttk.Button(btn_frame, text="动作空间 (norm)", command=self.open_action_space_norm,
                  style='Game.TButton', takefocus=0).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(4,0))

        # 帮助信息
        help_frame = ttk.LabelFrame(control_frame, height = 10, text="操作帮助", padding="5")
        help_frame.pack(fill=tk.X, pady=(0, 10))

        self.help_label = ttk.Label(help_frame, text=self.get_help_text(), font=self.font_small,
                                    wraplength=200, justify=tk.LEFT)
        self.help_label.pack(fill = tk.X, expand=True)
        
    def create_game_area(self, parent):
        """创建游戏区域（自适应宽度）"""
        game_frame = ttk.LabelFrame(parent, text="🎮 游戏区域", padding="10")
        game_frame.grid(row=0, column=1, sticky=(tk.W, tk.E, tk.N, tk.S), padx=10)
        
        # 创建Canvas
        self.canvas = tk.Canvas(game_frame, bg=self.colors['background'], highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True)
        
        # 绑定Canvas事件
        self.canvas.bind("<Configure>", self.on_canvas_configure)
        self.canvas.bind("<Button-1>", self.on_canvas_click)
    
    def create_info_panel(self, parent):
        """创建信息面板（自适应宽度）"""
        info_frame = ttk.LabelFrame(parent, text="📊 游戏信息", padding="10")
        info_frame.grid(row=0, column=2, sticky=(tk.W, tk.E, tk.N, tk.S), padx=(0, 10))
    

        # 游戏状态
        status_frame = ttk.LabelFrame(info_frame, text="状态信息", padding="5")
        status_frame.pack(fill=tk.X, pady=(0, 10))
        
        self.status_label = ttk.Label(status_frame, text="准备中...", font=self.font_medium)
        self.status_label.pack()
        
        self.step_label = ttk.Label(status_frame, text="步数: 0", font=self.font_small)
        self.step_label.pack()

        # 规则显示
        rules_frame = ttk.LabelFrame(info_frame, text="当前规则", padding="5")
        rules_frame.pack(fill=tk.X, pady=(0, 10))
        
        self.rules_text = tk.Text(rules_frame, height=6, width=25,
                                 font=self.font_medium, bg=self.colors['background'],
                                 fg=self.colors['text'], wrap=tk.WORD)
        self.rules_text.pack(fill=tk.X)
        

        
        # 前置条件信息
        pre_frame = ttk.LabelFrame(info_frame, text="前置条件", padding="5")
        pre_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        
        self.pre_text = tk.Text(pre_frame, height=6, width=25,
                                font=self.font_medium, bg=self.colors['background'],
                                fg=self.colors['text'], wrap=tk.WORD)
        self.pre_text.pack(fill=tk.BOTH, expand=True)
        
        # 变化信息
        cha_frame = ttk.LabelFrame(info_frame, text="变化", padding="5")
        cha_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        
        self.cha_text = tk.Text(cha_frame, height=6, width=25,
                                font=self.font_medium, bg=self.colors['background'],
                                fg=self.colors['text'], wrap=tk.WORD)
        self.cha_text.pack(fill=tk.BOTH, expand=True)
        
        # 交互信息
        inter_frame = ttk.LabelFrame(info_frame, text="交互", padding="5")
        inter_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        
        self.inter_text = tk.Text(inter_frame, height=6, width=25,
                                  font=self.font_medium, bg=self.colors['background'],
                                  fg=self.colors['text'], wrap=tk.WORD)
        self.inter_text.pack(fill=tk.BOTH, expand=True)
        
    def get_help_text(self):
        """获取帮助文本"""
        if self.current_mode == "game":
            return pad_status("键盘快捷键:\nW - 向上移动\nS - 向下移动\nA - 向左移动\nD - 向右移动\n空格 - 等待\nZ - 撤销\nR - 重启\nQ - 退出")
        elif self.current_mode == "analysis":
            return pad_status("分析模式操作:\n左键点击 - 选择社区\n再次点击 - 查看路径\n清除高亮 - 重置选择")

        elif self.current_mode == "edit":
            return pad_status("编辑模式操作:\n左键点击 - 选择并清空\n箭头键 - 移动选中位置\n名词: B(Bone), S(Sun\n对象: b(bone), s(sun)\n属性: 1(Push), 2(You)\n3(Win), 4(Stop), 5(Defeat)\n操作符: 0(IS)")

        elif self.current_mode == "replay":
            return pad_status("回放模式:\n输入uid和map开始\n自动按CSV动作序列执行")
        return ""
    
    def switch_mode(self):
        """切换模式"""
        self.current_mode = self.mode_var.get()
        
        if self.current_mode == "game":
            self.game_mode.set_grid(self.grid)
            self.analysis_mode.clear_selection()
        elif self.current_mode == "analysis":
            self.analysis_mode.set_grid(self.grid)
        elif self.current_mode == "edit":
            self.edit_mode.set_grid(self.grid)
            # 确保画布获取焦点，使方向键/空格仅作用于编辑
            if hasattr(self, 'canvas'):
                self.canvas.focus_set()
        elif self.current_mode == "replay":
            self.replay_mode.set_grid(self.grid)
            self.prompt_and_start_replay()
        
        # 更新帮助文本
        self.help_label.config(text=self.get_help_text())
        self.update_display()

    def prompt_and_start_replay(self):
        """弹出对话框，输入uid和map，加载地图并开始回放"""
        try:
            # Windows下强制切换到英文输入法（US）
            # self._force_english_ime()
            uid_str = simpledialog.askstring("回放", "请输入Uid (整数):", parent=self.root)
            if uid_str is None:
                return
            uid = int(uid_str)
            # 再次确保英文输入
            # self._force_english_ime()
            map_name = simpledialog.askstring("回放", "请输入地图名 (例如 intro):", parent=self.root)
            if not map_name:
                return
            # 加载地图
            filepath = f"levels/{map_name}.txt"
            self.load_map_from_file(filepath)
            # 载入动作序列
            actions, times = self.replay_mode.load_actions(uid, map_name)
            if not actions:
                messagebox.showwarning("无动作", "未找到匹配的动作序列")
                return
            # 设置replay的grid引用
            self.replay_mode.set_grid(self.grid)
            # 开始回放
            self.replay_mode.start(actions, times)
        except ValueError:
            messagebox.showerror("输入错误", "Uid 必须是整数")

    def _force_english_ime(self):
        """在Windows上将当前线程输入法切换为英文(US)。其他平台无操作。"""
        try:
            if sys.platform.startswith('win'):
                user32 = ctypes.WinDLL('user32', use_last_error=True)
                # 00000409 对应英语(美国)布局
                hkl = user32.LoadKeyboardLayoutW('00000409', 1)
                if hkl:
                    user32.ActivateKeyboardLayout(hkl, 0)
        except Exception:
            # 忽略切换失败，继续正常流程
            pass
    
    def load_grid(self):
        """加载网格"""
        self.grid = Analysis.from_text(self.map_text)
        
        if self.current_mode == "game":
            self.game_mode.set_grid(self.grid)
        elif self.current_mode == "analysis":
            self.analysis_mode.set_grid(self.grid)
        elif self.current_mode == "edit":
            self.edit_mode.set_grid(self.grid)
    
    def update_display(self):
        """更新显示

        将状态更新提前：先更新状态栏，再绘制地图。这样可以在绘制或更新地图时发生异常或耗时操作
        时，状态栏仍然能及时反映游戏结果（例如 Defeat/Win）。同时对地图绘制和信息显示
        添加异常保护，避免单个子步骤抛异常导致整体无法完成状态更新。
        """
        # 先更新状态栏（快速）——保证 outcome 等信息能被立即呈现
        try:
            self.update_status()
        except Exception as e:
            print(f"update_status 出错: {e}")

        # 再绘制游戏区域（可能耗时/出错）
        try:
            self.update_game_area()
        except Exception as e:
            print(f"update_game_area 出错: {e}")

        # 规则和信息显示也放在后面并用保护块包裹
        try:
            self.update_rules()
        except Exception as e:
            print(f"update_rules 出错: {e}")

        try:
            self.update_info_displays()
        except Exception as e:
            print(f"update_info_displays 出错: {e}")

    def calculate_layout(self):
        """计算画布布局参数"""
        # 检查Canvas尺寸是否已初始化
        if not hasattr(self, 'canvas_width') or not hasattr(self, 'canvas_height'):
            if hasattr(self, 'canvas'):
                # 强制更新Canvas尺寸
                self.canvas.update_idletasks()
                self.canvas_width = self.canvas.winfo_width()
                self.canvas_height = self.canvas.winfo_height()
                
                # 如果仍然为0，使用默认值
                if self.canvas_width <= 0 or self.canvas_height <= 0:
                    self.canvas_width = 800
                    self.canvas_height = 600
            else:
                return None
        
        # 确保尺寸为正数
        if self.canvas_width <= 0 or self.canvas_height <= 0:
            print(f"警告: Canvas尺寸无效 width={self.canvas_width}, height={self.canvas_height}")
            return None
        # 为坐标轴预留空间
        coord_space = 30
        
        # 计算可用画布尺寸（减去坐标轴空间）
        available_width = self.canvas_width - coord_space
        available_height = self.canvas_height - coord_space
        
        # 让游戏地图只占据90%的空间
        map_width = available_width * 0.9
        map_height = available_height * 0.9
        
        # 计算方形格子的尺寸
        cell_size = min(map_width / self.grid.width, 
                    map_height / self.grid.height)
        
        # 计算实际使用的画布尺寸
        actual_width = cell_size * self.grid.width
        actual_height = cell_size * self.grid.height
        
        # 计算偏移量（居中显示）
        offset_x = (self.canvas_width - actual_width) / 2
        offset_y = (self.canvas_height - actual_height) / 2
        
        self.layout = {
            'coord_space': coord_space,
            'available_width': available_width,
            'available_height': available_height,
            'map_width': map_width,
            'map_height': map_height,
            'cell_size': cell_size,
            'actual_width': actual_width,
            'actual_height': actual_height,
            'offset_x': offset_x,
            'offset_y': offset_y
        }

    def update_game_area(self):
        """更新游戏区域显示"""
        self.canvas.delete("all")
        self.calculate_layout()
        self.draw_coordinates(self.layout['offset_x'], self.layout['offset_y'], self.layout['cell_size'])
        self.draw_grid(self.layout['offset_x'], self.layout['offset_y'], self.layout['cell_size'])
        self.draw_entities(self.layout['offset_x'], self.layout['offset_y'], self.layout['cell_size'])

    def draw_coordinates(self, offset_x, offset_y, cell_size):
        """绘制坐标轴"""
        # 绘制水平坐标（0, 1, 2, 3...）在下方
        for x in range(self.grid.width):
            x_pos = offset_x + x * cell_size + cell_size / 2
            y_pos = offset_y + self.grid.height * cell_size + 20
            self.canvas.create_text(x_pos, y_pos, text=str(x), 
                                  font=self.font_small, fill=self.colors['coordinate'])
        
        # 绘制垂直坐标（从下到上：0, 1, 2, 3...）
        for y in range(self.grid.height):
            x_pos = offset_x - 20
            # 从下往上数：最下面一行是0，最上面一行是height-1
            display_y = self.grid.height - 1 - y
            y_pos = offset_y + y * cell_size + cell_size / 2
            self.canvas.create_text(x_pos, y_pos, text=str(display_y), 
                                  font=self.font_small, fill=self.colors['coordinate'])
    
    def draw_grid(self, offset_x, offset_y, cell_size):
        """绘制网格"""
        # 绘制垂直线
        for x in range(self.grid.width + 1):
            x_pos = offset_x + x * cell_size
            self.canvas.create_line(x_pos, offset_y, x_pos, 
                                  offset_y + self.grid.height * cell_size,
                                  fill=self.colors['grid'], width=1)
        
        # 绘制水平线
        for y in range(self.grid.height + 1):
            y_pos = offset_y + y * cell_size
            self.canvas.create_line(offset_x, y_pos, 
                                  offset_x + self.grid.width * cell_size, y_pos,
                                  fill=self.colors['grid'], width=1)
    
    def draw_entities(self, offset_x, offset_y, cell_size):
        """绘制实体"""
        for y in range(self.grid.height):
            for x in range(self.grid.width):
                # 反转y坐标以匹配print(gridmap)的显示
                display_y = self.grid.height - 1 - y
                tile = self.grid.get_tile((x, display_y))
                if tile and len(tile.entities) > 0:
                    self.draw_tile_entities(tile, x, y, offset_x, offset_y, cell_size)
    
    def draw_tile_entities(self, tile, x, y, offset_x, offset_y, cell_size):
        """绘制格子中的实体"""
        x_pos = offset_x + x * cell_size
        y_pos = offset_y + y * cell_size
        
        # 检查是否需要高亮显示
        coord = (x, self.grid.height - 1 - y)
        should_highlight = False
        highlight_color = None
        
        if self.current_mode == "analysis":
            # 获取对应的社区
            if 'com' in self.grid.observers:
                com_graph = self.grid.get('com', 'nodes')
                for com in com_graph:
                    if coord in com.coords:
                        if com.id in self.analysis_mode.highlighted_paths:
                            should_highlight = True
                            highlight_color = '#276E8B'  # 天蓝色 (SkyBlue)
                        if com.id in self.analysis_mode.highlighted_coms:
                            should_highlight = True
                            highlight_color = '#90862C'  # 卡其色 (Khaki)
        
        # 如果需要高亮，先绘制背景
        if should_highlight:
            self.canvas.create_rectangle(x_pos, y_pos, x_pos + cell_size, y_pos + cell_size,
                                       fill=highlight_color, width=0)
        
        # 计算实体在格子中的位置
        if tile.is_single():
            # 单个实体，居中显示
            entity = tile.get_first_entity()
            self.draw_entity(entity, x_pos + cell_size/2, y_pos + cell_size/2, cell_size)
        elif tile.is_multi():
            # 多个实体，分区域显示
            for i, entity in enumerate(tile.get_all_entities()):
                if i >= 4:
                    break
                sub_x = x_pos + (i % 2) * cell_size/2
                sub_y = y_pos + (i // 2) * cell_size/2
                self.draw_entity(entity, sub_x + cell_size/4, sub_y + cell_size/4, cell_size/2)
    
    def draw_entity(self, entity, x, y, size):
        """绘制单个实体"""
        entity_id = entity.get_entity_id()
        # if entity_id == '.':
        #     return 
        # 验证size参数
        size = max(size, 20)
        
        # 尝试加载贴图
        texture = self.get_entity_texture(entity_id, size)
        
        if texture:
            self.canvas.create_image(x, y, image=texture)
        else:
            # 回退到彩色矩形
            color = self.get_entity_color(entity_id)
            self.canvas.create_rectangle(x - size/2, y - size/2, 
                                       x + size/2, y + size/2,
                                       fill=color, outline='white', width=1)
    
    def get_entity_texture(self, entity_id, size):
        """获取实体贴图"""
        cache_key = f"{entity_id}_{size}" if size else entity_id

        if cache_key in self.texture_cache:
            return self.texture_cache[cache_key]
        
        try:
            texture_file = entity_id_to_texture(entity_id)
            texture_path = os.path.join(self.texture_path, texture_file)
            
            if os.path.exists(texture_path):
                image = Image.open(texture_path)
                
                # 修复：只有当size大于0时才进行resize操作
                if size and size > 0:
                    image = image.resize((int(size), int(size)), Image.Resampling.LANCZOS)

                texture = ImageTk.PhotoImage(image)
                self.texture_cache[cache_key] = texture
                return texture
        except Exception as e:
            print(f"加载贴图失败: {e}, entity_id: {entity_id}, size: {size}")
            if 'texture_path' in locals():
                print(f"  texture_path: {texture_path}")
        
        return None
    
    def get_entity_color(self, entity_id):
        """获取实体颜色"""
        colors = {
            'B': '#ff6b6b', 'C': '#4ecdc4', 'D': '#45b7d1', 'P': '#96ceb4', 'S': '#feca57',
            'b': '#ff9ff3', 'c': '#54a0ff', 'd': '#5f27cd', 'p': '#00d2d3', 's': '#ff9f43',
            '0': '#ff6348', '1': '#2ed573', '2': '#1e90ff', '3': '#ffa502', '4': '#ff3838', '5': '#ff6b6b'
        }
        return colors.get(entity_id, '#95a5a6')
    
    def update_status(self):
        """更新状态显示"""
        if self.current_mode == "game":
            status_text = self.game_mode.get_status()
        elif self.current_mode == "analysis":
            status_text = self.analysis_mode.get_status()
        elif self.current_mode == "edit":
            status_text = self.edit_mode.get_status()
        else:
            status_text = self.replay_mode.get_status()
        self.status_label.config(text=status_text)
        self.step_label.config(text=f"步数: {self.game_mode.step_count}")
    
    def update_rules(self):
        """更新规则显示"""
        # self.grid.update_rules()
        self.rules_text.delete(1.0, tk.END)
        rules = self.grid.rule_manager.detect_all_rules()
        for rule in rules:
            self.rules_text.insert(tk.END, str(rule) + "\n")
    
    def update_info_displays(self):
        """更新信息显示（前置条件、变化、交互）"""
        try:
            # 检查是否有必要的属性
            if not hasattr(self.grid, 'observers') or not hasattr(self.grid, 'add_observer'):
                # 不是 Analysis 类型，显示提示
                self.pre_text.delete(1.0, tk.END)
                self.cha_text.delete(1.0, tk.END)
                self.inter_text.delete(1.0, tk.END)
                self.pre_text.insert(tk.END, "仅在Analysis模式可用")
                self.cha_text.insert(tk.END, "仅在Analysis模式可用")
                self.inter_text.insert(tk.END, "仅在Analysis模式可用")
                return
            
            # 添加 info observer
            if 'info' not in self.grid.observers:
                self.grid.add_observer('info')
            
            # 检查 before 状态
            if self.grid.get('info', 'before') is None:
                return
            
            # 获取 info 数据
            info = self.grid.get('info', 'info')
            
            # 删除旧内容
            self.pre_text.delete(1.0, tk.END)
            self.cha_text.delete(1.0, tk.END)
            self.inter_text.delete(1.0, tk.END)
            
            # 插入新内容
            pre_content = format_info_dict(info.get('pre', {}))
            cha_content = format_info_dict(info.get('cha', {}))
            inter_content = format_info_dict(info.get('inter', {}))
            self.pre_text.insert(tk.END, pre_content)
            self.cha_text.insert(tk.END, cha_content)
            self.inter_text.insert(tk.END, inter_content)
        except Exception as e:
            # 发生错误时显示错误信息，避免程序卡死
            error_msg = f"错误: {str(e)[:50]}"
            try:
                self.pre_text.delete(1.0, tk.END)
                self.cha_text.delete(1.0, tk.END)
                self.inter_text.delete(1.0, tk.END)
                self.pre_text.insert(tk.END, error_msg)
                self.cha_text.insert(tk.END, error_msg)
                self.inter_text.insert(tk.END, error_msg)
            except:
                pass  # 如果连显示错误都失败了，就忽略

    def event_to_coord(self, event):
        """将Canvas点击事件转换为网格坐标"""
        canvas_x = event.x
        canvas_y = event.y
        self.calculate_layout()
        # 计算点击的格子坐标
        grid_x = int((canvas_x - self.layout['offset_x']) / self.layout['cell_size'])
        grid_y = int((canvas_y - self.layout['offset_y']) / self.layout['cell_size'])
        
        # 检查是否在有效范围内
        if 0 <= grid_x < self.grid.width and 0 <= grid_y < self.grid.height:
            # 修复y坐标反转问题
            display_y = self.grid.height - 1 - grid_y
            return (grid_x, display_y)
        
        return None
    
    def on_canvas_click(self, event):
        """处理Canvas点击事件"""
        if self.current_mode == "analysis":
            coord = self.event_to_coord(event)
            if coord:
                status = self.analysis_mode.select_community(coord)
                self.status_label.config(text=status)
                self.update_display()  # 不更新status，保持新设置的status
        elif self.current_mode == "edit":
            coord = self.event_to_coord(event)
            if coord:
                self.edit_mode.select_coord(coord)
                self.grid = self.edit_mode.grid
                self.update_display()
    
    def on_canvas_configure(self, event):
        """Canvas尺寸变化事件"""
        self.canvas_width = event.width
        self.canvas_height = event.height
        self.calculate_layout()
        self.update_display()
    
    def bind_events(self):
        """绑定键盘事件"""
        # 只在画布上绑定键盘，使方向键/空格不受右栏控件影响
        self.canvas.focus_set()
        self.canvas.bind('<KeyPress>', self.on_key_press)
    
    def on_key_press(self, event):
        """处理键盘事件"""
        if self.current_mode == "game":
            try:
                action = Action.from_char(event.char.lower())
                self.game_mode.step(action)
                # 同步更新TkinterGame的grid引用
                self.grid = self.game_mode.grid
                self.update_display()
            except ValueError:
                pass
        elif self.current_mode == "edit":
            # 编辑模式：处理键盘输入
            # 过滤特殊按键
            if event.keysym in ['Shift_L', 'Shift_R', 'Caps_Lock', 'Control_L', 'Control_R', 'Alt_L', 'Alt_R']:
                return
            
            # 处理清空坐标
            if event.keysym == 'space':
                self.edit_mode.clear_coord()
                self.update_display()
                return
            
            # 处理箭头键
            if event.keysym in ['Up', 'Down', 'Left', 'Right']:
                direction_map = {'Up': 'up', 'Down': 'down', 'Left': 'left', 'Right': 'right'}
                direction = direction_map[event.keysym]
                status = self.edit_mode.move_selection(direction)
                self.status_label.config(text=status)
                self.update_display()
                return
            
            # 处理实体输入
            entity_id = event.char
            if entity_id:  # 确保不是空字符
                status = self.edit_mode.add_entity(entity_id)
                self.status_label.config(text=status)
                self.grid = self.edit_mode.grid
                self.update_display()
    
    def load_intro_map(self):
        """加载intro地图"""
        self.load_map_from_file("levels/intro.txt")
    
    def load_tutorial_map(self):
        """加载tutorial地图"""
        self.load_map_from_file("levels/tutorial.txt")
    
    def load_base_map(self):
        """加载base地图"""
        self.load_map_from_file("levels/base.txt")

    def load_target_map(self):
        """加载target地图"""
        self.load_map_from_file("levels/target.txt")
    
    def load_map_from_file(self, filepath):
        """从文件加载地图"""
        self.game_mode.step_count = 0
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                map_text = f.read().strip()
            
            # 验证地图格式
            test_grid = Analysis.from_text(map_text)
            self.map_text = map_text
            self.load_grid()
            self.update_display()
            
        except FileNotFoundError:
            messagebox.showerror("文件不存在", f"地图文件不存在: {filepath}")
        except Exception as e:
            messagebox.showerror("加载失败", f"无法加载地图文件 {filepath}: {e}")
     
    def load_selected_map(self):
        """从levels文件夹选择地图文件"""
        # 确保levels目录存在
        levels_dir = "levels"
        if not os.path.exists(levels_dir):
            messagebox.showwarning("目录不存在", "levels目录不存在，请先创建一些地图文件")
            return
        
        # 打开文件选择对话框
        filepath = filedialog.askopenfilename(
            title="选择地图文件",
            initialdir=levels_dir,
            filetypes=[("文本文件", "*.txt"), ("所有文件", "*.*")]
        )
        
        if filepath:
            self.load_map_from_file(filepath)

    def create_empty_map(self):
        """创建空地图"""
        self.game_mode.step_count = 0
        dialog = EmptyMapDialog(self.root)
        self.root.wait_window(dialog.dialog)
        
        if dialog.result:
            width, height = dialog.result
            # 创建空地图字符串
            empty_map = '.' * width + '\n'
            empty_map = empty_map * height
            empty_map = empty_map.rstrip('\n')
            
            self.map_text = empty_map
            self.load_grid()
            self.update_display()
    
    def save_map(self):
        """保存地图"""
        if self.current_mode != "edit":
            messagebox.showwarning("保存失败", "请在编辑模式下保存地图")
            return
        
        # 弹出对话框输入文件名
        filename = simpledialog.askstring("保存地图", "请输入文件名（不含扩展名）:", 
                                        initialvalue="my_map")
        
        if filename:
            try:
                # 确保levels目录存在
                levels_dir = "levels"
                if not os.path.exists(levels_dir):
                    os.makedirs(levels_dir)
                
                # 生成地图文本
                map_text = self.grid.save_text()
                
                # 保存文件
                filepath = os.path.join(levels_dir, f"{filename}.txt")
                with open(filepath, 'w', encoding='utf-8') as f:
                    f.write(map_text)
                
                messagebox.showinfo("保存成功", f"地图已保存到: {filepath}")
                
            except Exception as e:
                messagebox.showerror("保存失败", f"保存地图时出错: {e}")
    
    def run(self):
        """运行游戏"""
        self.root.mainloop()


class EmptyMapDialog:
    """空地图对话框"""
    
    def __init__(self, parent):
        self.result = None
        
        # 创建对话框窗口
        self.dialog = tk.Toplevel(parent)
        self.dialog.title("新建空地图")
        self.dialog.geometry("300x200")
        self.dialog.resizable(False, False)
        self.dialog.transient(parent)
        self.dialog.grab_set()
        
        # 居中显示
        self.dialog.geometry("+%d+%d" % (parent.winfo_rootx() + 50, parent.winfo_rooty() + 50))
        
        # 创建界面
        self.create_widgets()
    
    def create_widgets(self):
        """创建界面组件"""
        main_frame = ttk.Frame(self.dialog, padding="20")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # 标题
        title_label = ttk.Label(main_frame, text="设置地图尺寸", font=("Arial", 12, "bold"))
        title_label.pack(pady=(0, 20))
        
        # 宽度输入
        width_frame = ttk.Frame(main_frame)
        width_frame.pack(fill=tk.X, pady=(0, 10))
        
        ttk.Label(width_frame, text="宽度:").pack(side=tk.LEFT)
        self.width_var = tk.StringVar(value="8")
        width_entry = ttk.Entry(width_frame, textvariable=self.width_var, width=10)
        width_entry.pack(side=tk.RIGHT)
        
        # 高度输入
        height_frame = ttk.Frame(main_frame)
        height_frame.pack(fill=tk.X, pady=(0, 20))
        
        ttk.Label(height_frame, text="高度:").pack(side=tk.LEFT)
        self.height_var = tk.StringVar(value="6")
        height_entry = ttk.Entry(height_frame, textvariable=self.height_var, width=10)
        height_entry.pack(side=tk.RIGHT)
        
        # 按钮
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill=tk.X)
        
        ttk.Button(button_frame, text="确定", command=self.ok_clicked).pack(side=tk.RIGHT, padx=(5, 0))
        ttk.Button(button_frame, text="取消", command=self.cancel_clicked).pack(side=tk.RIGHT)
    
    def ok_clicked(self):
        """确定按钮点击"""
        try:
            width = int(self.width_var.get())
            height = int(self.height_var.get())
            
            if width < 1 or height < 1:
                messagebox.showerror("输入错误", "宽度和高度必须大于0")
                return
            
            self.result = (width, height)
            self.dialog.destroy()
            
        except ValueError:
            messagebox.showerror("输入错误", "请输入有效的数字")
    
    def cancel_clicked(self):
        """取消按钮点击"""
        self.dialog.destroy()

def main():
    """主函数"""
    # 创建游戏实例
    game = TkinterGame()
    
    # 运行游戏
    game.run()

if __name__ == "__main__":
    main()