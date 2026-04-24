"""Lightweight CSV -> Gridmap state index builder.

This module provides a single function `build_state_index_from_csv` that iterates a CSV,
reconstructs a Grid (using `analyzer.Analysis.from_text` by default), computes the
Gridmap.summary() and inserts the summary into the class-level `Gridmap.state_index` map
so lookups by state key are O(1).
"""

import hashlib
from base_gameLogic import GameEngine, Action, GameHistory, GameOutcome
from state_graphic import Graphic
from state_storage import get_data_manager
from state_analyzer import StateAnalyzer
from trans_analyzer import TransAnalyzer
from util import decoding, encoding




from typing import TYPE_CHECKING, Dict, Any
if TYPE_CHECKING:
    from recorder import State, Trans
    from plan_hierachy import Plan, PlanBuilder

# -------------------------
# Gridmap and TargetInteraction
# -------------------------

STATE_HASH_HEX_LENGTH = 16  # 使用前16个十六进制字符作为状态哈希键

class Gridmap(GameEngine):
    """ Gridmap是没有记忆的 """
    dm = get_data_manager()

    @property
    def key(self) -> 'StateKey':
        return self.quick_save()
    
    def quick_save(self) -> 'StateKey':
        return StateKey.from_gridmap(self)
    
    @classmethod
    def quick_load(cls, data, history=None) -> 'State':
        raw_data = cls.dm.get_gamestate(data)['raw']
        grid = cls.quick_load_helper(raw_data)
        grid.game_history = history or GameHistory(grid)
        return grid


class Hybrid(GameEngine):

    def __init__(self, state, history=None):
        self.gridmap = state
        self.state = GameOutcome.__getitem__('Continue')
        self.game_history = history or GameHistory(self)

    def quick_save(self):
        return self.gridmap.get_str()
    
    @classmethod
    def quick_load(cls, statekey, history=None):
        return cls(State(key=statekey), history=history)

    def _handle_movement(self, action: Action):
        trans = self.gridmap.to_trans(action)
        self.gridmap = trans.to_state()
        chain = trans.describe(False)['push_chain']
        self.state = GameOutcome.__getitem__(self.gridmap.describe(False)['outcome'])
        self.game_history.add_record(action, self)
        return self, self.state, chain
    
    def __repr__(self):
        return self.quick_save()
    
    @classmethod
    def from_text(cls, text):
        grid = GameEngine.from_text(text)
        return cls(State(grid))

class StateKey(str):
    
    @classmethod
    def from_gridmap(cls, grid: 'Gridmap') -> 'StateKey':
        saved = grid.quick_save_helper().encode('utf-8')
        full_digest = hashlib.sha256(saved).hexdigest()
        key_str = 'S-' + full_digest[:STATE_HASH_HEX_LENGTH]
        return cls(key_str)

    def __repr__(self):
        return str(self) 
    
class State:
    # class-level data manager (shared across subclasses)
    def __init__(self, grid: 'Gridmap'=None, key: 'StateKey'=None) -> 'State':

        if (grid is None and key is None) or (grid is not None and key is not None):
            raise ValueError("Either grid or key must be provided, but not both.")
        
        self.manager = get_data_manager().gamestate_manager 
        self._grid = grid
        self.cls = grid.__class__ if grid else Gridmap
        self.raw = grid.quick_save_helper() if grid else None

        self.key = StateKey.from_gridmap(grid) if grid else StateKey(str(key))

        if self.key not in self.manager:
            self.describe(False)
        
        self.raw = self.manager[self.key].get('raw')
    
    @classmethod
    def from_key(cls, key: 'StateKey') -> 'State':
        key = StateKey(str(key))
        return cls(key=key)

    @property
    def analyzer(self) -> 'StateAnalyzer':
        # if self._grid is None:
        return StateAnalyzer(self)
    
    def show(self):
        return Graphic(self)()
    
    @property
    def plan_builder(self) -> 'PlanBuilder':
        from plan_hierachy import PlanBuilder
        return PlanBuilder(self)
    
    def rebuild_fresh(self) -> 'Gridmap':
        """ 强制重建 Gridmap，丢弃缓存 """
        self._grid = self.cls.quick_load_helper(self.raw)
        return self._grid

    def rebuild(self) -> 'Gridmap':
        """ 没有 _grid, 从 raw 重建 """
        if self._grid is None or self._grid.key != self.key:
            self._grid = self.cls.quick_load_helper(self.raw)
        return self._grid

    def describe(self, explain: bool = True) -> Dict[str, Any]:
        if self.key not in self.manager:
            summary = self.analyzer.sum_basic_features()
            summary['key'] = self.key
            summary['raw'] = self.raw
            summarize = {k: encoding(v) for k, v in summary.items()}
            self.manager[self.key] = summarize

        raw_result = self.manager[self.key]
        if not explain:
            return raw_result
        return {k: decoding(v) for k, v in raw_result.items()}

    def expand(self, method, force = False):
        description = self.describe(False)
        if force or method not in description:
            if hasattr(self.analyzer, f'get_{method}'):
                answer = getattr(self.analyzer, f'get_{method}')()
                self.manager[self.key][method] = encoding(answer)
                return answer
            raise KeyError(f"Method {method} not found in StateAnalyzer.")
        return decoding(description[method])
    
    def __getitem__(self, name: str) -> Any:
        return self.expand(name)
    
    
    def __eq__(self, other: 'State') -> bool:
        return self.key == other.key

    def to_plan(self, action_seq, thinning=False) -> 'Plan':
        return self.plan_builder.build_plan(action_seq, thinning)[0]
    
    def to_unit(self, action_seq) -> 'Plan':
        return self.plan_builder.quick_build_unit(action_seq)
    
    def to_trans(self, action: Action, post_state: 'State' = None) -> 'Trans':
        return Trans(self, action, post_state)
    
    def get_str(self):
        return str(self.key)
    
    def __repr__(self):
        return self.key.__repr__()
    
class Trans:

    def __init__(self, pre_state: State, action: Action, post_state: State = None) -> 'Trans':

        self.manager = get_data_manager().target_manager
        self.key = TransKey.from_step(pre_state, action)
        self.pre_state = pre_state
        self.action = action
        self._post_state = post_state
        self.certainy = not action.is_undo()
        if self.key not in self.manager:
            self.describe(False)

    def show(self):
        g = Graphic(self.pre_state)
        for (x, y) in self.pre_state['agents']:
            g.add_arrow((0, 255, 0), x, y, self.action.value[0])
        return g()
    
    @property
    def analyzer(self) -> 'TransAnalyzer':
        return TransAnalyzer(self)


    def describe(self, explain: bool = True):

        if self.key not in self.manager:
            summary = self.analyzer.sum_basic_features()
            summary['key'] = self.key
            summary['pre_state'] = self.pre_state.key
            summary['action'] = self.action.value
            summarize = {k: encoding(v) for k, v in summary.items()}
            if self.certainy:
                self.manager[self.key] = summarize
            raw_result = summarize
        else:
            raw_result = self.manager[self.key]

        if not explain:
            return raw_result
        return {k: decoding(v) for k, v in raw_result.items()}
    
    def expand(self, method, force = False):
        description = self.describe(False)
        if force or method not in description:
            if hasattr(self.analyzer, f'get_{method}'):
                answer = getattr(self.analyzer, f'get_{method}')()
                self.manager[self.key][method] = answer
                return decoding(answer)
            raise KeyError(f"Method {method} not found in TransAnalyzer.")
        return decoding(description[method])
    
    def __getitem__(self, name: str) -> Any:
        return self.expand(name)
    
    # def __getattr__(self, name: str) -> Any:
    #     try:
    #         return self.expand(name)
    #     except KeyError:
    #         raise AttributeError
    
    def __eq__(self, other: 'Trans') -> bool:
        if self.certainy and other.certainy:
            return self.key == other.key
        return self.key == other.key and self.post_state == other.post_state
    
    def to_state(self) -> 'State':
        if self._post_state is not None:
            return self._post_state
        return State(key=self['post_state'])
        
    def to_plan(self) -> 'Plan':
        from plan_hierachy import NewPlanStep
        return NewPlanStep(self.pre_state, self)
    
    def __repr__(self):
        return self.key.__repr__()
    
    @classmethod
    def from_key(cls, key: 'TransKey') -> 'Trans':
        key = TransKey(str(key))
        pre_state_key, action_key = key.split('_', 1)
        pre_state = State.from_key(pre_state_key)
        action = Action(action_key)
        return cls(pre_state, action)
    
class TransKey(str):

    @staticmethod
    def from_step(pre_state: 'State', action: Action) -> 'TransKey':
        key_str = f"{pre_state.key}_{action.value}"
        return TransKey(key_str)
    
    @staticmethod
    def from_transition(trans: 'Trans') -> 'TransKey':
        key_str = f"{trans.pre_state.key}_{trans.action.value}"
        return TransKey(key_str)
    
    def __repr__(self):
        return f"T-{str(self)}"


