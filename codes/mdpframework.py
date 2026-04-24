from recorder import State, get_data_manager, StateKey
from base_gameLogic import GameOutcome, Action, GameEngine
from recorder import Gridmap

from pathlib import Path
from state_storage import get_data_manager
import util
from ui_graphic import Graphic
import os
from collections import defaultdict

import pandas as pd


def find_file(filename: str, start_path: Path = None, max_up: int = None) -> Path:
    p = Path(start_path) if start_path else Path.cwd()
    max_steps = max_up if max_up is not None else 6
    for _ in range(max_steps):
        candidate = p / filename
        if candidate.exists():
            return candidate, candidate.parent
        p = p.parent

    print(f"File '{filename}' not found")
    return None, None
    

class Environment:
    def __init__(self, engine=Gridmap, level_dir='levels', exp_dir=None):
        self.mm = MapManager(level_dir=level_dir, engine=engine)
        self.em = ExperienceManager(exp_dir=exp_dir) if exp_dir else None
        self.ui = Graphic()
        self.init_grid, self.grid = None, None
        self.outcome, self.chain = None, None
        self.exp_dir = exp_dir

    # ====== 被试数据管理 ======

    def init_experience(self, exp_dir=None):
        if exp_dir is not None:
            self.exp_dir = exp_dir
        self.em = ExperienceManager(exp_dir=self.exp_dir) if self.exp_dir else None
        return self.em
    
    # ====== Game Board ======

    def load_map(self, map_name: str):
        get_data_manager(f"../recording/{map_name}")
        self.init_grid = self.mm(map_name)
        self.grid = self.init_grid.deep_copy()
        self.outcome = 'Start'
        return self.grid
    
    def reset(self):
        if self.init_grid is not None:
            self.grid = self.init_grid.deep_copy()
            self.outcome = 'Restarted'
            self.chain = None

    @staticmethod
    def transition(grid: 'State', action_char: str):
        action = Action.from_char(action_char.lower())
        if not isinstance(action, Action):
            return grid, 'Invalid', None

        next_grid, outcome, chain = grid.step(action)
        return next_grid, outcome.name, chain
    
    def step(self, action_char: str):
        self.grid, self.outcome, self.chain = self.transition(self.grid, action_char) 

    def replay(self, action_seq: list[str], grid = None):
        if grid is None:
            self.reset()
        else:
            self.grid = grid.deep_copy()
        state_history = [str(self.grid.quick_save())]
        chain_history = []
        for action_char in action_seq:
            self.step(action_char)
            state_history.append(str(self.grid.quick_save()))
            chain_history.append(util.encoding(self.chain))
        return state_history, chain_history, self.outcome
    

    def inter_play(self, init_grid: 'State' = None):
        grid = init_grid or self.grid
        history = [str(self.grid.quick_save())]
        while True:
            action_char = input().strip().lower()
            grid, outcome, chain = self.transition(grid, action_char)
            history.append(str(grid.quick_save()))
            if grid.state == GameOutcome.Quit:
                break
        return history, outcome
    
    def inter_play_with_ui(self, init_grid: 'State' = None):
        grid = init_grid or self.grid
        while True:

            self.ui.clear_screen()
            self.ui.render_gridworld(grid)
            self.ui.render_state_summary(grid)
            action_char = self.ui.collect_user_action(grid)

            grid, outcome, chain = self.transition(grid, action_char)
            if grid.state == GameOutcome.Quit:
                break
        self.ui.summary(grid)
        return grid

    
    def replay_with_ui(self, action_seq: list[str], init_gird: 'State' = None, delay: float = 0.5):
        import time
        grid = init_gird or self.init_grid
        for action_char in action_seq:
            self.ui.clear_screen()
            self.ui.render_gridworld(grid)
            self.ui.render_state_summary(grid)
            time.sleep(delay)
            grid = self.transition(grid, action_char)
        return grid

# ======= Experience Managements =======
class ExperienceManager:

    def __call__(self, map_name: str = None, uid: int = None) -> pd.DataFrame:
        if map_name is not None:
            map_data = self._grouped_data.get(map_name, {})
            if uid is not None:
                return map_data.get(uid, pd.DataFrame())  # 不是copy
            return map_data
        return self._grouped_data
    
    def __init__(self, exp_dir: str, start_path=None, max_up=None):
        """
        Args:
            file_name: 要查找的文件名
            start_path: 开始搜索 levels/ 的路径（默认当前工作目录）
            max_up: 最多向上查找的层数
        """
        self.start_path = Path(start_path) if start_path else Path.cwd()
        self.max_up = max_up if max_up is not None else 6
        self.file_path, self.root_path = self.find_exp_file(exp_dir)
        self._grouped_data = self.load_grouped_df()

    def find_exp_file(self, file_name: str) -> Path:
        """向上查找指定文件"""
        return find_file(file_name, self.start_path, self.max_up)

    def save_exp_file(self, file_name: str = None, cover = False):
        if not self._grouped_data:
            print("No experience data to save.")
            return
        df = self.rebuild_total_df()
        save_path = self.root_path / file_name if not cover else self.file_path
        util.save_df_with_schema(df, save_path)
        print(f"Experience data saved to {save_path}")
    
    def iter_epoch(self, map_name: str = None):
        if map_name is not None:
            print(f"Iterating map {map_name} with {len(self._grouped_data.get(map_name, {}))} ids.")
            map_data = self._grouped_data.get(map_name, {})
            for uid, df in map_data.items():
                yield (map_name, uid), df
        else:
            for map_name, map_data in self._grouped_data.items():
                print(f"Iterating map {map_name} with {len(map_data)} ids.")
                for uid, df in map_data.items():
                    yield (map_name, uid), df


    def load_grouped_df(self) -> pd.DataFrame:
        """读取经验数据文件为 DataFrame"""
        if not self.file_path:
            raise FileNotFoundError("Experience file not found.")
        df = util.load_df_with_schema(self.file_path)

        grouped = defaultdict(dict)
        for (map_name, uid), group in df.groupby(['Map', 'Uid'], observed=True):
            grouped[map_name][uid] = group.reset_index(drop=True)
        del df
        return grouped
    
    def rebuild_total_df(self, map: str = None) -> pd.DataFrame:
        """重建完整的经验数据 DataFrame"""
        if not self._grouped_data:
            return pd.DataFrame()
        df_list = []

        if map is not None:
            uids_dict = self._grouped_data.get(map, {})
            df_list.extend(uids_dict.values())
            return pd.concat(df_list, ignore_index=True)
        
        for uids_dict in self._grouped_data.values():
            df_list.extend(uids_dict.values())
        return pd.concat(df_list, ignore_index=True)
    
    
    
# ======= Map Management =======
class MapManager:
    """管理地图文件的加载与 Gridmap 实例化"""

    def load_map_cont(self, map_name: str) -> str:
        """加载指定地图文件内容"""
        if map_name not in self.raw_maps:
            raise ValueError(f"Map '{map_name}' not found. Available: {list(self.raw_maps.keys())}")
        return self.engine.from_text(self.raw_maps[map_name])
    
    def load_map_conts(self) -> dict[str, 'State']:
        """加载所有地图文件内容"""
        return {name: self.engine.from_text(content) for name, content in self.raw_maps.items()}
    

    def list_map_files(self):
        """列出所有可用的地图名"""
        return list(self.raw_maps.keys())
    
    def __call__(self, map_name: str = None) -> 'State':
        if map_name is None:
            self.grid_maps = self.load_map_conts()
            return
        if self.grid_maps and map_name in self.grid_maps:
            grid = self.grid_maps[map_name]
            return grid, State(grid)
        return self.load_map_cont(map_name)

    def __init__(self, level_dir=None, start_path=None, max_up=None, engine=None):

        level_dir = level_dir if level_dir else 'levels'
        self.engine = State if engine is None else engine
        self.start_path = Path(start_path) if start_path else Path.cwd()
        self.max_up = max_up if max_up is not None else 6
        self.levels_dir, self.root_dir = self.find_level_file(level_dir)
        self.raw_maps = self.load_map_raw()
        self.grid_maps = None

    def find_level_file(self, level_dir: str) -> Path:
        """向上查找 levels/ 目录"""
        return find_file(level_dir, self.start_path, self.max_up)
    
    def load_map_raw(self):
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
        self.init_grid = self.mm._prepare_map(map_name)  # Gridmap instance
        self.costFn = costFn if costFn else self.defaultCostFn
    
    # ====== initialization ======
    def configure_storage(self, map_name):
        storage_dir = f'./state_recording/{map_name}'
        pass

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
        grid = State.quick_load(self.cache[state_idx])
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
            grid = State.rebuild(state_idx)
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

if __name__ == "__main__":
    env = Environment(GameEngine)
    env.load_map('tutorial')
    env.inter_play_with_ui()