"""目标交互摘要器 - 负责生成 TargetInteraction 的摘要和索引

将原本在 TargetInteraction 中的摘要生成逻辑分离出来。
"""

from typing import TYPE_CHECKING, Optional, Dict, Any, Union
from util import decoding, encoding
from state_storage import get_data_manager
from collections import defaultdict
from base_gameLogic import Coord, Tile, Action
from base_entity import Entity
import numpy as np

if TYPE_CHECKING:
    from recorder import State, TargetInteraction, Trans
    from base_gameLogic import Tile, Action
    from state_storage import DataManager

PUSH_CHAIN_COMPARE_BY = 'texture_chain'  # 全局设置 PushChain 比较依据

class PushChain:
    COMPARE_BY = PUSH_CHAIN_COMPARE_BY


    @classmethod
    def set_compare_by(cls, by: str):
        cls.COMPARE_BY = by

    @classmethod
    def from_raw_chain(cls, raw_chain: Any) -> 'PushChain':
        if isinstance(raw_chain, str):
            raw_chain = decoding(raw_chain)
        return cls(raw_chain)

    def __init__(self, chain: Dict[Coord, 'Tile']):
        self.content = chain

        self.full_chain = defaultdict(list)
        self._collision = []

        self.act = None
        for title, chain in self.content.items():
            act = self.analyze_chain(title, chain)
            if self.act is None and isinstance(act, Action) and act.is_special():
                self.act = act.name

    def analyze_chain(self, title: tuple, chain: list):
        origin_coord = Coord(title[:2])
        action = Action(title[2])
        if chain or action.is_special():
            self._collision.append(title)
        offset, current = 0, origin_coord
        for e in chain:
            entity = Entity.quick_load(e)
            if entity.get_coord() != current:
                offset += 1
                current = entity.get_coord()
            self.full_chain[offset].append(entity)
        return action

    @staticmethod
    def _to_hashable(value):
        """Recursively convert mutable containers to hashable forms."""
        if isinstance(value, dict):
            return tuple(sorted((PushChain._to_hashable(k), PushChain._to_hashable(v)) for k, v in value.items()))
        if isinstance(value, list):
            return tuple(PushChain._to_hashable(v) for v in value)
        if isinstance(value, set):
            return frozenset(PushChain._to_hashable(v) for v in value)
        if isinstance(value, tuple):
            return tuple(PushChain._to_hashable(v) for v in value)
        return value

    def describe_chain(self, func):
        if self.act is not None:
            return self.act
        ans = tuple(
            tuple(sorted(func(e) for e in tile))
            for tile in self.full_chain.values())
        return ans if len(ans) >= 1 else np.nan

    @property
    def texture_property_chain(self):

        return {offset: 
                set((t, p) for t, p in zip(self.full_result['texture'][offset], self.full_result['property'][offset]))
                for offset in self.full_result['globalid']}

    
    @property
    def _globalid_chain(self):
        return self.describe_chain(lambda e: e.get_global_id())
    @property
    def _texture_chain(self):
        return self.describe_chain(lambda e: e.get_entity_id())
    
    @property
    def _property_chain(self):
        return self.describe_chain(lambda e: e.get_prop_flag())
    
    @property
    def _complex_chain(self):
        return self.describe_chain(lambda e: (e.get_entity_id(), e.get_prop_flag()))
    
    @property
    def _full_chain(self):
        return self.describe_chain(lambda e: (e.get_global_id(), e.get_entity_id(), e.get_prop_flag()))
    
    @classmethod
    def full_chain(cls, chain):
        return cls.from_raw_chain(chain)._full_chain
    
    @classmethod
    def texture_chain(cls, chain):
        return cls.from_raw_chain(chain)._texture_chain
    
    @classmethod
    def property_chain(cls, chain):
        return cls.from_raw_chain(chain)._property_chain
    
    @classmethod
    def globalid_chain(cls, chain):
        return cls.from_raw_chain(chain)._globalid_chain
    
    @classmethod
    def complex_chain(cls, chain):
        return cls.from_raw_chain(chain)._complex_chain

    
    
    @property
    def collision(self):
        return self._collision
    
    @property
    def target_chain(self):
        return self.__getattribute__(self.COMPARE_BY)
    
    def is_empty(self) -> bool:
        """链是否为空，判断 Step 到 Unit"""
        return not bool(self._collision)
    
    def __eq__(self, other: 'PushChain') -> bool:
        """链完全相等, 判断 Unit 到 Chunk"""
        return self._globalid_chain == other._globalid_chain
    
    def __le__(self, other: 'PushChain') -> bool:
        """链包含关系，判断 Chunk 到 Seq"""
        self_chain = self.target_chain
        other_chain = other.target_chain
        for key, val1 in self_chain.items():
            if key not in other_chain or not set(val1).issubset(set(other_chain.get(key))):
                return False
        return True
    
    def __and__(self, other: 'PushChain') -> bool:
        """链交集关系，判断 Seq 到 Subgoal"""
        self_chain = self.target_chain
        other_chain = other.target_chain
        self_entity = set(e for tile in self_chain.values() for e in tile)
        other_entity = set(e for tile in other_chain.values() for e in tile)
        return not self_entity.isdisjoint(other_entity)
    
    def __ge__(self, other: 'PushChain') -> bool:
        return other.__le__(self)
    
    def __repr__(self):
        return repr(self.content)

class TransAnalyzer:

    def __init__(self, trans: 'Trans'):
        self.pre_state = trans.pre_state
        self.action = trans.action
        self.trans = trans
        self.post_state, self.chain = self.simulation()


    def simulation(self) -> str:
        if self.trans._post_state is None:
            from recorder import State
            self.pre_state.rebuild_fresh()
            grid, _, chain = self.pre_state._grid.step(self.action)
            if len(chain) == 0:
                print(self.pre_state, grid, chain, self.action)
            return State(grid), PushChain.from_raw_chain(chain)
        else:
            return self.trans._post_state, self.special_push_chain()
    
    def special_push_chain(self):
        # assert self.action.is_special(), "Only special actions have special push chains."
        yous = self.pre_state.rebuild_fresh().get_agent()
        if not yous:
            return PushChain({(-2, -2, self.action.value): []})
        return PushChain({(e.get_x(), e.get_y(), self.action.value): [] for e in yous})
    
    def sum_basic_features(self) -> Dict[str, Any]:
        features = {
            'post_state': self.post_state.key,
            # 'fake_state': self.get_fake_state().key,
            'push_chain': self.chain.content,
            'action_cost': self.get_action_cost(),
            'plan_cost': self.get_plan_cost(),
        }
        return features
    
    def get_action_cost(self) -> int:
        return 1 if not self.action.is_quit() else 0
    
    def get_plan_cost(self) -> int:
        if self.chain.is_empty():
            return 0
        return sum(len(c) for c in self.chain.content.values())
    
    def get_fake_state(self) -> str:
        from recorder import State
        if not self.action.is_move():
            return self.post_state
        
        self.pre_state.reset()
        for you in self.pre_state._grid.get_agent():
            next_tile = self.action.get_neighbor_tile(you, self.pre_state._grid)
            # 没有递归调用push chain
            for entity in next_tile.get_all_entities():
                if 'PUSH' in entity.get_prop() or 'TEXT' in entity.get_prop():
                    self.pre_state._grid.move_entity(entity, self.action.get_neighbor_coord(next_tile.coord))
            self.pre_state._grid.move_entity(you, next_tile.coord)

        fake_state = State(self.pre_state._grid)
        # 没有规则更新
        # 没有碰撞检测
        return fake_state

