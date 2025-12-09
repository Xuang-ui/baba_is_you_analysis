"""状态摘要器 - 负责生成完整的状态摘要和哈希

将原本在 Gridmap 中的摘要生成逻辑分离出来。
"""

from typing import TYPE_CHECKING, Optional, Dict, Any
import json
import hashlib
from base_gameLogic import STATE_HASH_HEX_LENGTH, GameOutcome, Action
from state_analyzer import StateAnalyzer
from util import decoding, encoding

if TYPE_CHECKING:
    from recorder import Gridmap, TargetInteraction


class StateSummarizer:
    """负责生成完整的状态摘要"""
    
    def __init__(self, analyzer: StateAnalyzer, data_manager):
        """初始化 StateSummarizer
        
        Args:
            analyzer: StateAnalyzer 实例，用于计算状态特征
            data_manager: DataManager 实例，统一管理所有索引
        """
        self.analyzer = analyzer
        self.data_manager = data_manager
    
    # 通过属性访问 managers（保持向后兼容）
    @property
    def gamestate_manager(self):
        return self.data_manager.gamestate_manager
    
    @property
    def target_manager(self):
        return self.data_manager.target_manager
    
    @property
    def plan_manager(self):
        return self.data_manager.plan_manager
    
    @property
    def state_manager(self):
        return self.data_manager.gamestate_manager
    
    @property
    def interaction_manager(self):
        return self.data_manager.target_manager
    
    @property
    def action_manager(self):
        return self.data_manager.plan_manager
    
    def compute_hash(self, grid: 'Gridmap', updating: bool = True) -> str:
        """计算状态哈希键"""
        saved = grid.quick_save().encode('utf-8')
        full_digest = hashlib.sha256(saved).hexdigest()
        state_key = full_digest[:STATE_HASH_HEX_LENGTH]
        
        # 如果需要更新且状态不在索引中，创建摘要
        if updating and state_key not in self.gamestate_manager:
            # 使用 updating=True 确保完整展开（包括 target 索引）
            self.summary(grid, precomputed_state_key=state_key, updating=True)
        
        return state_key
    
    def summary(self, grid: 'Gridmap', precomputed_state_key: Optional[str] = None, 
                      updating: bool = True) -> Dict[str, Any]:
        """生成完整的状态摘要
        
        Args:
            grid: 游戏状态
            precomputed_state_key: 预计算的状态键（避免重复计算）
            updating: 是否展开交互并存储到索引（True=完整展开，False=只计算不存储）
        """
        from recorder import TargetInteraction
        
        # 计算或使用预计算的状态键
        if precomputed_state_key is None:
            state_key = self.compute_hash(grid, updating=False)
        else:
            state_key = precomputed_state_key
        
        # 检查缓存
        cached = self.gamestate_manager.get(state_key)
        if cached is not None:
            # 如果需要展开且缓存中没有目标交互信息，则重新计算
            if updating and not cached['inter']:
                pass  # 继续重新计算
            else:
                return cached
        
        # 计算各种特征
        raw = grid.quick_save()
        _, man_dist, _, num_reachable, game_dist, _, bound_dist, _ = self.analyzer.get_distances(grid)
        
        info = {
            'rules': encoding(self.analyzer.get_rules(grid)),
            'tokens': encoding(self.analyzer.get_token_counts(grid)),
            'num_prop': encoding(self.analyzer.get_prop_counts(grid)),
            'objects': encoding(self.analyzer.get_basic_counts(grid)),
            'targets': encoding(num_reachable),
        }
        
        # 距离信息
        man_dist_list = [min(man_dist[k], 9999) for k in self.analyzer.PROP_KEYS]
        game_dist_list = [min(game_dist[k], 9999) for k in self.analyzer.PROP_KEYS]
        bound_dist_list = [min(bound_dist[k], 9999) for k in self.analyzer.PROP_KEYS]
        com_dist_list = self.analyzer.get_greedy_community(grid)
        com_dist_list = [min(com_dist, 9999) for com_dist in com_dist_list]
        
        dist = {
            'man': man_dist_list,
            'game': game_dist_list,
            'bound': bound_dist_list,
            'com': com_dist_list
        }
        
        # 目标交互信息
        targets = self._get_interaction(grid)
        # 如果 updating=True，确保所有 target 都被索引
        inter_list = [target._get_action_hash(updating=False) for target in targets]
        
        
        # 组装摘要
        summary_dict = {
            'state_key': state_key,
            'game_state': str(grid.state),
            'info': info,
            'dist': dist,
            'inter': inter_list,
            'raw': raw
        }
        
        # 存储到管理器
        self.gamestate_manager[state_key] = summary_dict
        return summary_dict
    
    def _get_interaction(self, grid: 'Gridmap'):
        """从所有 YOU 的位置出发，分析可能的目标交互"""
        from util import Deque
        from recorder import TargetInteraction
        
        all_you = grid.get_entities_by_prop('YOU')
        if not all_you:
            return []

        you_coords = [you.get_coord() for you in all_you]
        queue = Deque()
        visited = set()
        targets = []

        for coord in you_coords:
            queue.push((coord, 1))
            visited.add(coord)

        while not queue.isEmpty():
            coord, dist = queue.pop()
            for action in (Action.up, Action.down, Action.left, Action.right):
                neighbor_coord = action.get_neighbor_coord(coord)
                if neighbor_coord.bound:
                    continue

                if neighbor_coord not in visited:
                    neighbor_tile = grid.get_tile(neighbor_coord)
                    if neighbor_tile.is_empty():
                        visited.add(neighbor_coord)
                        queue.push((neighbor_coord, dist + 1))
                        continue
                    
                    targets.append(TargetInteraction(coord, action, dist, grid))

        return targets
    
    def expand(self, grid: 'Gridmap') -> Dict[str, Any]:
        """展开状态（确保所有交互都被索引）"""
        targets = self._get_interaction(grid)
        for target in targets:
            target._get_action_hash(updating=True)