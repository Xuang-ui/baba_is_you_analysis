"""Plan 价值管理器 - 从 plan['summary'] 读取价值评分

价值评分存储在 plan['summary'] = {'raw': {...}, 'norm': {...}} 中。
此管理器提供统一的访问接口，优先从 plan 直接读取，缓存作为备用。
"""

from typing import Dict, Optional
import pandas as pd
import threading


class PlanValueManager:
    """管理 ActionPlan 的价值评分（从 plan['summary'] 读取）"""
    
    def __init__(self, plan_manager=None):
        """初始化价值管理器
        
        Args:
            plan_manager: ActionPlan 索引管理器（可选，用于从 plan 读取 summary）
        """
        self.plan_manager = plan_manager
        self._value_cache: Dict[str, Dict[str, float]] = {}  # 备用缓存
        self._lock = threading.RLock()
    
    def set_plan_manager(self, plan_manager):
        """设置 plan_manager（延迟初始化）"""
        self.plan_manager = plan_manager
    
    def get_value(self, plan_key: str, use_norm: bool = True) -> Optional[Dict[str, float]]:
        """获取 ActionPlan 的价值评分
        
        优先从 plan['summary'] 读取，如果不存在则从缓存读取。
        
        Args:
            plan_key: ActionPlan 键
            use_norm: 是否使用归一化的值（True=norm, False=raw）
        
        Returns:
            价值评分字典，如 {'man_greedy': 0.5, 'rules': 0.3, ...}
        """
        with self._lock:
            # 优先从 plan['raw'] 或 plan['norm'] 读取
            if self.plan_manager is not None:
                plan = self.plan_manager.get(plan_key)
                if plan:
                    if use_norm and 'norm' in plan and plan['norm']:
                        return plan['norm']
                    elif not use_norm and 'raw' in plan and plan['raw']:
                        return plan['raw']
            
            # 备用：从缓存读取
            return self._value_cache.get(plan_key)
    
    def set_value(self, plan_key: str, value_dict: Dict[str, float]):
        """设置 ActionPlan 的价值评分
        
        Args:
            plan_key: ActionPlan 键
            value_dict: 价值评分字典
        """
        with self._lock:
            self._value_cache[plan_key] = value_dict
    
    def update_values_from_dataframe(self, df: pd.DataFrame):
        """从 DataFrame 批量更新 ActionPlan 价值
        
        Args:
            df: 归一化后的评分 DataFrame，index 为 plan_key
        """
        with self._lock:
            self._value_cache.update(df.to_dict(orient='index'))
    
    def get_best_plan(self, plan_keys: list, metric: str = 'man_greedy', use_norm: bool = True) -> Optional[str]:
        """从候选 ActionPlan 中选择最佳的
        
        Args:
            plan_keys: 候选 ActionPlan 键列表
            metric: 评价指标
            use_norm: 是否使用归一化的值
        
        Returns:
            最佳 ActionPlan 键
        """
        best_key = None
        best_value = -float('inf')
        
        for key in plan_keys:
            values = self.get_value(key, use_norm=use_norm)
            if values and metric in values:
                if values[metric] > best_value:
                    best_value = values[metric]
                    best_key = key
        
        return best_key
    
    def get_plan_ranking(self, plan_keys: list, metric: str = 'man_greedy', use_norm: bool = True) -> list:
        """对候选 ActionPlan 进行排序
        
        Args:
            plan_keys: 候选 ActionPlan 键列表
            metric: 评价指标
            use_norm: 是否使用归一化的值
        
        Returns:
            排序后的 ActionPlan 键列表（从高到低）
        """
        scored_plans = []
        for key in plan_keys:
            values = self.get_value(key, use_norm=use_norm)
            if values and metric in values:
                scored_plans.append((key, values[metric]))
        
        # 按分数降序排列
        scored_plans.sort(key=lambda x: x[1], reverse=True)
        return [key for key, _ in scored_plans]
    
    def clear(self):
        """清空所有缓存的价值评分"""
        with self._lock:
            self._value_cache.clear()
    
    def __len__(self):
        return len(self._value_cache)
    
    def __repr__(self):
        return f"PlanValueManager(values={len(self._value_cache)})"


# ========== 全局单例 ==========

_plan_value_manager: Optional[PlanValueManager] = None


def get_plan_value_manager() -> PlanValueManager:
    """获取全局 PlanValueManager 单例"""
    global _plan_value_manager
    if _plan_value_manager is None:
        _plan_value_manager = PlanValueManager()
    return _plan_value_manager
