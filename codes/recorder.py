"""Lightweight CSV -> Gridmap state index builder.

This module provides a single function `build_state_index_from_csv` that iterates a CSV,
reconstructs a Grid (using `analyzer.Analysis.from_text` by default), computes the
Gridmap.summary() and inserts the summary into the class-level `Gridmap.state_index` map
so lookups by state key are O(1).
"""
import json
from typing import Optional, Callable
import pandas as pd
from base_entity import Entity
from base_gameLogic import Action, Deque, RuleManager, STATE_HASH_HEX_LENGTH, GameOutcome, GameEngine, Tile
import hashlib
import threading
import os
from util import Deque, PriorityQueue
from collections import deque
from state_storage import IndexManager, get_state_index_manager, get_action_index_manager, get_plan_index_manager
from state_analyzer import StateAnalyzer
from state_summarizer import StateSummarizer
from plan_evaluator import PlanValueEvaluator
from plan_value_manager import get_plan_value_manager
from state_solver import PuzzleSolver
from community_graph import CoordSet, Community, CommunityGraph
from target_simulator import TargetSimulator
from target_summarizer import TargetSummarizer

# -------------------------
# DataManager - 统一管理三类索引
# -------------------------

class DataManager:
    """统一的数据管理器，管理 GameState、TargetInteraction、ActionPlan 三类索引"""
    
    _instance: Optional['DataManager'] = None
    
    def __init__(self):
        """初始化三个索引管理器"""
        self.gamestate_manager = get_state_index_manager()       # GameState 索引
        self.target_manager = get_action_index_manager()         # TargetInteraction 索引
        self.plan_manager = get_plan_index_manager()             # ActionPlan 索引
        
        # 设置 plan_value_manager 的 plan_manager（用于从 plan['summary'] 读取）
        plan_value_mgr = get_plan_value_manager()
        plan_value_mgr.set_plan_manager(self.plan_manager)
        
        # 向后兼容的别名
        self.state_manager = self.gamestate_manager
        self.interaction_manager = self.target_manager
        self.action_manager = self.plan_manager
    
    @classmethod
    def get_instance(cls) -> 'DataManager':
        """获取单例实例"""
        if cls._instance is None:
            cls._instance = DataManager()
        return cls._instance
    
    @classmethod
    def reset(cls):
        """重置所有索引（用于测试）"""
        if cls._instance is not None:
            cls._instance.gamestate_manager.clear()
            cls._instance.target_manager.clear()
            cls._instance.plan_manager.clear()
            # 同时清空价值管理器
            get_plan_value_manager().clear()
            # 同时清空价值管理器
            get_plan_value_manager().clear()
    
    def get_gamestate(self, state_key: str):
        """获取游戏状态摘要"""
        return self.gamestate_manager.get(state_key)
    
    def set_gamestate(self, state_key: str, state_summary: dict):
        """存储游戏状态摘要"""
        self.gamestate_manager[state_key] = state_summary
    
    def get_target(self, target_key: str):
        """获取目标交互摘要"""
        return self.target_manager.get(target_key)
    
    def set_target(self, target_key: str, target_summary: dict):
        """存储目标交互摘要"""
        self.target_manager[target_key] = target_summary
    
    def get_plan(self, plan_key: str):
        """获取动作计划"""
        return self.plan_manager.get(plan_key)
    
    def set_plan(self, plan_key: str, plan_data: dict):
        """存储动作计划"""
        self.plan_manager.put(plan_key, plan_data)
    
    # 向后兼容的别名方法
    def get_state(self, state_key: str):
        return self.get_gamestate(state_key)
    
    def set_state(self, state_key: str, state_summary: dict):
        self.set_gamestate(state_key, state_summary)
    
    def get_interaction(self, interaction_key: str):
        return self.get_target(interaction_key)
    
    def set_interaction(self, interaction_key: str, interaction_summary: dict):
        self.set_target(interaction_key, interaction_summary)
    
    def get_action(self, action_key: str):
        return self.get_plan(action_key)
    
    def set_action(self, action_key: str, action_data: dict):
        self.set_plan(action_key, action_data)
    
    def __repr__(self):
        return (f"DataManager(gamestates={len(self.gamestate_manager.keys())}, "
                f"targets={len(self.target_manager.keys())}, "
                f"plans={len(self.plan_manager)})")


def get_data_manager() -> DataManager:
    """获取全局数据管理器实例"""
    return DataManager.get_instance()


# -------------------------
# Gridmap and TargetInteraction
# -------------------------

class Gridmap(GameEngine):
    # class-level data manager (shared across subclasses)
    _data_manager: Optional[DataManager] = None
    PROP_KEYS = ['YOU', 'WIN', 'PUSH', 'DEFEAT', 'STOP', 'TEXT', 'REGULAR', 'EMPTY']
    
    def __init__(self, width=8, height=6, simu_depth=10):
        """初始化 Gridmap 和所有分析组件"""
        super().__init__(width, height)
        # 获取统一的 DataManager
        data_mgr = self.get_data_manager()
        # 初始化分析组件
        self.analyzer = StateAnalyzer()
        self.summarizer = StateSummarizer(self.analyzer, data_mgr)
        self.evaluator = PlanValueEvaluator(self.summarizer)
        self.solver = PuzzleSolver(self.summarizer)
        self.target_simulator = TargetSimulator(data_mgr, simu_depth)
        self.target_summarizer = TargetSummarizer(self.target_simulator)
    
    def __getitem__(self, key):
        """通过 state_key 获取状态摘要"""
        return self.get_state_info(key)

    @classmethod
    def get_state_info(cls, state_key, feature_key=None):
        """ hash 到 summary"""
        index = cls.get_gamestate_manager()
        assert state_key in index, f"Wrong state key {state_key}"
        try_feature = cls._get_state_info_fast(state_key, feature_key)
        if try_feature is not None:
            return try_feature
        return cls._get_state_info_slow(state_key, feature_key)
    
    @classmethod
    def rebuild(cls, state_key):
        """ hash 到 Gridmap 实例"""
        raw = cls.get_state_info(state_key, 'raw')[:]  # [:] 复制以防修改
        return cls.quick_load(raw)

    def get_state_idx(self):
        """ Gridmap 实例到 hash"""
        return self._get_state_hash()

    @classmethod
    def clear_state_index(cls):
        """清空状态索引"""
        cls.get_gamestate_manager().clear()

    # ============ 索引管理器访问方法 ============
    @classmethod
    def get_data_manager(cls) -> DataManager:
        """获取统一数据管理器（懒初始化）"""
        if cls._data_manager is None:
            cls._data_manager = get_data_manager()
        return cls._data_manager
    
    @classmethod
    def get_gamestate_manager(cls) -> IndexManager:
        """获取 GameState 索引管理器"""
        return cls.get_data_manager().gamestate_manager
    
    @classmethod
    def get_target_manager(cls) -> IndexManager:
        """获取 TargetInteraction 索引管理器"""
        return cls.get_data_manager().target_manager
    
    @classmethod
    def get_plan_manager(cls):
        """获取 ActionPlan 管理器（PlanManager）"""
        return cls.get_data_manager().plan_manager
    
    @classmethod
    def get_state_manager(cls) -> IndexManager:
        """[向后兼容] 委托给 get_gamestate_manager"""
        return cls.get_gamestate_manager()

    @classmethod
    def _get_state_info_fast(cls, state_key, feature_key=None):
        index = cls.get_gamestate_manager()
        state_sum = index.get(state_key)
        if not feature_key:
            return state_sum
        return state_sum.get(feature_key, None) if state_sum else None
    
    @classmethod
    def _get_state_info_slow(cls, state_key, feature_key=None):
        index = cls.get_gamestate_manager()
        grid = Gridmap.quick_load(index[state_key]['raw'])
        state_sum = grid.expand()
        return state_sum if feature_key is None else state_sum.get(feature_key, None)
    
    # ============ 向后兼容适配器 (Backward Compatibility Adapters) ============
    # 这些方法保留旧的 API 签名，内部委托给新的分离类
    
    def describe(self, precomputed_state_key=None, updating=True):
        """[适配器] 委托给 StateSummarizer"""
        return self.summarizer.summary(self, precomputed_state_key, updating)
    
    def evaluate(self, type = 'action'):
        """[适配器] 委托给 PlanValueEvaluator.evaluate_plan_space"""
        full_result = self.evaluator.evaluate_plan_space(self)
        mapping = {'action': 0, 'raw': 1, 'norm': 2}
        if isinstance(type, str):
            return full_result[mapping[type]]
        elif isinstance(type, list):
            return [full_result[mapping[t]] for t in type]
        
    
    def expand(self):
        """[适配器] 委托给 StateSummarizer"""
        return self.summarizer.expand(self)
    
    def solving(self, max_depth: int = 3):
        """[适配器] 委托给 PuzzleSolver"""
        return self.solver.bfs_solve(self, max_depth)
    
    def _check_yous(self):
        """[适配器] 委托给 StateAnalyzer"""
        return StateAnalyzer.check_yous(self)
    
    def _get_basic_counts(self):
        """[适配器] 委托给 StateAnalyzer"""
        return StateAnalyzer.get_basic_counts(self)
    
    def _get_token_counts(self):
        """[适配器] 委托给 StateAnalyzer"""
        return StateAnalyzer.get_token_counts(self)
    
    def _get_distances(self):
        """[适配器] 委托给 StateAnalyzer"""
        return StateAnalyzer.get_distances(self)
    
    def _get_rules(self):
        """[适配器] 委托给 StateAnalyzer"""
        return StateAnalyzer.get_rules(self)
    
    def _get_greedy_community(self):
        """[适配器] 委托给 StateAnalyzer"""
        return StateAnalyzer.get_greedy_community(self)
    
    def _get_state_hash(self, updating=True):
        """[适配器] 委托给 StateSummarizer"""
        return self.summarizer.compute_hash(self, updating)
    
    def _get_interaction(self):
        """[适配器] 委托给 StateSummarizer"""
        return self.summarizer._get_interaction(self)


class TargetInteraction:
    """目标交互类 - 描述对特定目标单元格的抽象交互意图
    
    只负责描述交互的基本信息，不再包含模拟逻辑。
    模拟逻辑由 TargetSimulator 处理。
    """
    
    @classmethod
    def get_target_manager(cls) -> IndexManager:
        """获取 TargetInteraction 索引管理器"""
        return Gridmap.get_data_manager().target_manager
    
    @classmethod
    def get_action_manager(cls) -> IndexManager:
        """[向后兼容] 委托给 get_target_manager"""
        return cls.get_target_manager()
    
    def __init__(self, start, action, dist, gridmap):
        self.start, self.action, self.dist, self.gridmap = start, action, dist, gridmap
        self.collision = action.get_neighbor_coord(start)
        
        # 使用 TargetSummarizer 计算推动链
        summarizer = gridmap.target_summarizer
        self.chain = summarizer.calculate_push_chain(self)
        self.dir = self.chain[0] if self.chain else []
        self.ind = summarizer.generate_indirect_tile(self, self.chain)
        self.index = summarizer.compute_chain_index(self)

    def simulation(self):
        """[适配器] 委托给 TargetSimulator"""
        simulator = self.gridmap.target_simulator
        return simulator.simulate_target(self)
    
    def get_chain_index(self):
        """Unique index: statehash_actionname_collisioncoord"""
        return self.gridmap.target_summarizer.compute_chain_index(self)
    
    def _get_chain_index(self):
        """[向后兼容] 使用 get_chain_index"""
        return self.get_chain_index()
    
    def _get_action_hash(self, updating=True):
        """获取目标交互的哈希键，并在需要时模拟并存储"""
        return self.gridmap.target_summarizer.get_or_create_hash(self, updating)
    
    # [已迁移] _get_transition 和 _get_tile_info 已迁移到 InteractionSimulator
    
    def summary(self, precomputed_action_key=None):
        """获取目标交互摘要（向后兼容）"""
        return self.gridmap.target_summarizer.create_summary(
            self, precomputed_key=precomputed_action_key, updating=True)

    @classmethod
    def clear_action_index(cls):
        """清空动作索引（向后兼容）"""
        Gridmap.get_data_manager().target_manager.clear()
    
    def get_description(self):
        """[适配器] 委托给 TargetSummarizer"""
        return self.gridmap.target_summarizer.get_description(self)
    
    def __repr__(self):
        return self.get_description()


# ============ 向后兼容别名 (Backward Compatibility Aliases) ============
Interaction = TargetInteraction  # 保持旧代码兼容性

# [已迁移] CoordSet, Community, CommunityGraph 已迁移到 community_graph.py
# [已迁移] describe_single_action 已迁移到 state_evaluator.py 的 ActionSpaceEvaluator.describe_single_action
