"""拼图求解器 - 负责 BFS 搜索解决方案

将原本在 Gridmap 中的 solving() 方法分离出来。
"""

from typing import TYPE_CHECKING, List, Tuple, Dict, Any
from collections import deque

if TYPE_CHECKING:
    from recorder import State
    from state_summarizer import StateSummarizer
    from base_gameLogic import GameOutcome


class PuzzleSolver:
    """负责使用 BFS 搜索求解拼图"""
    
    def __init__(self, summarizer: 'StateSummarizer'):
        """初始化 PuzzleSolver
        
        Args:
            summarizer: StateSummarizer 实例，用于生成状态摘要
        """
        self.summarizer = summarizer
    
    def bfs_solve(self, start_grid: 'State', max_depth: int = 10) -> List[List[Tuple[int, int]]]:
        """使用 BFS 搜索所有达到胜利状态的路径
        
        Args:
            start_grid: 起始游戏状态
            max_depth: 最大搜索深度
        
        Returns:
            所有解决方案路径的列表，每条路径是 [(action_sample, action_idx)] 的列表
        """
        from recorder import State, TargetInteraction
        from base_gameLogic import GameOutcome
        
        # 确保起始状态被索引
        start_key = self.summarizer.compute_hash(start_grid, updating=True)
        
        # 通过 data_manager 访问 managers
        data_mgr = self.summarizer.dm
        
        # BFS 队列: (state_key, path, depth)
        queue = deque([(start_key, [], 0)])
        solutions = []
        
        while queue:
            current_key, path, depth = queue.popleft()
            
            if depth >= max_depth:
                continue
            
            current_state = data_mgr.gamestate_manager.get(current_key)
            if current_state is None:
                continue
            
            # 检查是否胜利
            outcome = current_state['info']['outcome']
            if outcome == GameOutcome.WIN.value:
                solutions.append(path)
                continue
            
            # 展开当前状态（如果尚未展开）
            if not current_state['inter']['inters']:
                # 重建 grid 并展开
                temp_grid = State(1, 1)
                temp_grid.quick_load(current_state['info']['save_tuple'])
                self.summarizer.expand(temp_grid)
                current_state = data_mgr.gamestate_manager.get(current_key)
            
            # 探索所有目标交互
            for action_sample in current_state['inter']['inters']:
                interact = data_mgr.target_manager.get(action_sample)
                if interact is None:
                    continue
                
                for action_idx, next_key in interact['trans']['post_state'].items():
                    new_path = path + [(action_sample, action_idx)]
                    queue.append((next_key, new_path, depth + 1))
        
        return solutions
    
    def describe_solution(self, solution_path: List[Tuple[int, int]]) -> Dict[str, Any]:
        """将解决方案路径转换为可读描述
        
        Args:
            solution_path: [(action_sample, action_idx)] 列表
        
        Returns:
            包含步骤数、动作列表等信息的字典
        """
        # 通过 data_manager 访问 target_manager
        data_mgr = self.summarizer.dm
        
        steps = []
        for action_sample, action_idx in solution_path:
            interact = data_mgr.target_manager.get(action_sample)
            if interact:
                # 可以提取更多信息，如 move 等
                steps.append({
                    'action_sample': action_sample,
                    'action_idx': action_idx,
                    'dist': interact['trans'].get('dist', None)
                })
        
        return {
            'num_steps': len(solution_path),
            'steps': steps,
            'path': solution_path
        }
