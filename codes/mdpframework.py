from recorder import Gridmap, get_data_manager
from base_gameLogic import GameOutcome, Action
from pathlib import Path
from state_storage import configure_json_storage, save_all_data
import util

# ======= Map Management =======
class MapManager:
    """管理地图文件的加载与 Gridmap 实例化"""
    
    def prepare_map(self, map_name=None, summary=False):
        """
        准备地图并返回 Gridmap 实例或字典。
        
        Args:
            map_name: 指定地图名（如 'tutorial'）。若为 None，返回所有地图的 Gridmap 字典。
        
        Returns:
            单个 Gridmap 实例（如果指定 map_name）或 dict[str, Gridmap]（所有地图）
        """
        if map_name:
            if map_name not in self.maps:
                raise ValueError(f"Map '{map_name}' not found. Available: {list(self.maps.keys())}")
            grid = Gridmap.from_text(self.maps[map_name])
            if summary:
                grid.describe()
            return grid
        else:
            grids = {}
            for name, text in self.maps.items():
                grids[name] = Gridmap.from_text(text)
                if summary:
                    grids[name].summary()
            return grids
    
    def list_maps(self):
        """列出所有可用的地图名"""
        return list(self.maps.keys())
    
    def __init__(self, start_path=None, max_up=6):
        """
        Args:
            start_path: 开始搜索 levels/ 的路径（默认当前工作目录）
            max_up: 最多向上查找的层数
        """
        self.start_path = Path(start_path) if start_path else Path.cwd()
        self.max_up = max_up
        self.levels_dir = self._find_levels_dir()
        self.maps = self._get_raw_map()

    def _find_levels_dir(self):
        """向上查找 levels/ 目录"""
        p = self.start_path
        for _ in range(self.max_up):
            cand = p / 'levels'
            if cand.exists() and cand.is_dir():
                return cand
            p = p.parent
        raise FileNotFoundError(f'Could not find levels/ directory in parents of {self.start_path}')
    
    def _get_raw_map(self):
        """读取 levels/ 下的所有 .txt 文件内容"""
        return {p.stem: p.read_text(encoding='utf-8') for p in self.levels_dir.glob('*.txt')}
    

# ======= General MDP Framework ======
class MarkovDecisionProcess:
    """通用马尔可夫决策过程（MDP）框架接口"""
    
    def getStartState(self):
        """返回初始状态的索引"""
        raise NotImplementedError()
    
    def getStates(self):
        """返回所有可能状态的索引列表"""
        raise NotImplementedError()
    
    def getPossibleActions(self, state_idx):
        """返回给定状态下可执行的动作索引列表"""
        raise NotImplementedError()
    
    def getNextState(self, state_idx, action_idx):
        """返回执行动作后到达的下一个状态索引"""
        raise NotImplementedError()
    
    def getReward(self, state_idx, action_idx, next_state_idx):
        """返回执行动作后获得的奖励值"""
        raise NotImplementedError()
    
    def isTerminal(self, state_idx):
        """判断给定状态是否为终止状态"""
        raise NotImplementedError()

class BabaMDP(MarkovDecisionProcess):
    def __init__(self, map_name, costFn):
        """初始化 Baba MDP 环境"""
        # 初始化地图，配置存储空间
        self.storage_backends = self.configure_storage(map_name)
        self.gamestate_backend, self.target_backend, self.plan_backend = self.storage_backends
        self.dm = get_data_manager()
        
        self.mm = MapManager()
        self.init_grid = self.mm.prepare_map(map_name)  # Gridmap instance
        self.costFn = costFn if costFn else self.defaultCostFn
    
    # ====== initialization ======
    def configure_storage(self, map_name):
        storage_dir = f'./state_recording/{map_name}'
        return configure_json_storage(storage_dir=storage_dir, auto_save=False)

    def save_result(self):
        save_all_data()

    @staticmethod
    def defaultCostFn(state, action, nextState):
        return 1  # default cost is 1 per action
    
    def getStartState(self):
        return self.init_grid.get_state_idx()

    def getStates(self):
        return self.dm.gamestate_manager.keys()
    
    def getReward(self, state_idx, action_idx, next_state_idx):
        return self.costFn(state_idx, action_idx, next_state_idx)
    
    def getGameOutcome(self, state_idx):
        return self.dm.get_gamestate(state_idx)['game_state']
    
    def isTerminal(self, state_idx):
        return self.getGameOutcome(state_idx) == "Win" # 终止状态包括胜利（和失败是后加见所用）

    def getPossibleActions(self, state_idx):
        """返回给定状态下可执行的动作索引列表"""
        raise NotImplementedError()
    
    def getNextState(self, state_idx, action_idx):
        """返回执行动作后到达的下一个状态索引"""
        raise NotImplementedError()

    def getActionShortForm(self, action_idx):
        return str(action_idx)

class BabaConcreteMDP(BabaMDP):
    def __init__(self, map_name, costFn=None):
        super().__init__(map_name, costFn)
        self.cache = {self.init_grid.get_state_idx(): self.init_grid.quick_save()}
    
    def getPossibleActions(self, state_idx):
        if self.getGameOutcome(state_idx) != 'Continue':
            return []
        return ['w', 'a', 's', 'd']

    def getNextState(self, state_idx, action_idx):
        grid = Gridmap.quick_load(self.cache[state_idx])
        action = Action.from_char(action_idx)
        next_grid, _, _ = grid.step(action)
        next_state = next_grid.get_state_idx()
        self.cache[next_state] = next_grid.quick_save()
        return next_state

class BabaAbstractMDP(BabaMDP):

    # ===== MDP Interface ======
    def getPossibleActions(self, state_idx):

        state_sum = self.dm.get_gamestate(state_idx)

        if self.getGameOutcome(state_idx) != 'Continue':
            return []
        
        targets = state_sum['inter']['inters']
        if not all(tar in self.dm.target_manager.keys() for tar in targets):
            # 完成展开，强制执行simulation
            grid = Gridmap.rebuild(state_idx)
            return grid.evaluate('action')
        else:
            return [plan for tar in targets for plan in self.dm.get_target(tar).get('plans', [])]
    
    def getNextState(self, state_idx, action_idx):
        if action_idx == 'restart':
            return self.getStartState()

        trans = self.dm.get_plan(action_idx)['parent']
        assert trans['init_gamestate'] == state_idx, "Invalid state transition"
        return trans['post_gamestate']

    def getActionShortForm(self, action_idx):
        return  ','.join([action_idx.split('_')[i] for i in [2, 3, 5]])

# ======== Search Methods ========
def BFS(problem: BabaMDP, max_solution = 1, max_depth = float('inf')) -> list[str]:
    """Search the shallowest nodes in the search tree first."""

    queue = util.Deque()
    visited = set()
    queue.push((problem.getStartState(), []))
    visited.add(problem.getStartState())
    solutions = []

    while not queue.isEmpty() and len(solutions) < max_solution:
        (current_state, path) = queue.pop()
        print(current_state, path)

        if len(path) >= max_depth:
            continue

        possible_actions = problem.getPossibleActions(current_state)
        if not possible_actions:
            continue

        for action in possible_actions:
            successor = problem.getNextState(current_state, action)
            if successor in visited:
                continue
            visited.add(successor)
            queue.push((successor, path + [action]))

            # action_str = problem.getActionShortForm(action)
            if problem.isTerminal(successor):
                solutions.append(path + [action])
                print(solutions[-1])


    return solutions


def DFS(problem: BabaMDP, max_solution = 1, max_depth = float('inf')) -> list[str]:
    """Search the shallowest nodes in the search tree first."""

    stack = util.Stack()
    visited = set()
    stack.push((problem.getStartState(), []))
    visited.add(problem.getStartState())

    solutions = []
    max_len = 0

    while not stack.isEmpty() and len(solutions) < max_solution:
        (current_state, path) = stack.pop()

        if len(path) >= max_depth:
            continue

        for action in problem.getPossibleActions(current_state):
            successor = problem.getNextState(current_state, action)\
            
            if problem.isTerminal(successor):
                solutions.append(path + [problem.getActionShortForm(action)])
                continue

            if successor in visited:
                continue
            visited.add(successor)
            stack.push((successor, path + [action]))
    return solutions