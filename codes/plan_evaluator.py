"""Plan 价值评估器 - 负责评估 ActionPlan 的价值

从 state_evaluator.py 重命名而来，专注于计算 plan 的 value。
"""

from typing import TYPE_CHECKING, Dict, Any, Tuple
import pandas as pd
from util import jaccard_similarity

if TYPE_CHECKING:
    from recorder import State
    from state_summarizer import StateSummarizer


class PlanValueEvaluator:
    """负责评估 ActionPlan 的价值"""
    
    def __init__(self, summarizer: 'StateSummarizer'):
        """初始化 PlanValueEvaluator
        
        Args:
            summarizer: StateSummarizer 实例，用于生成状态摘要
        """
        self.summarizer = summarizer
    
    def evaluate_plan_space(self, grid: 'State') -> Tuple[list, pd.DataFrame, pd.DataFrame]:
        """评估当前网格的所有 ActionPlan，返回 (action_index_list, raw_df, normalized_df)
        
        评估基于每个 plan 的 pre_gamestate，结果存储到 plan 中
        
        Returns:
            action_index_list: 所有 plan_key 的列表
            raw_df: 包含每个 plan 的原始价值分数的 DataFrame
            normalized_df: 每列使用平均秩归一化到 [0,1] 的 DataFrame
        """
        from recorder import State
        grid.expand()
        current_state = self.summarizer.summary(grid)
        action_space = current_state['inter']
        rows = {}
        action_index_list = []
        
        # 通过 data_manager 访问 managers
        data_mgr = self.summarizer.dm
        
        for target_key in action_space:
            target = data_mgr.target_manager.get(target_key)
            if target is None:
                continue
            
            # 遍历该 target 的所有 plans
            plans = target.get('plans', [])
            for plan_key in plans:
                plan = data_mgr.plan_manager.get(plan_key)
                if plan is None:
                    continue
                
                # 评估该 plan（基于其 pre_gamestate）
                value = self.evaluate_plan(plan)
                if value is not None:
                    rows[plan_key] = value
                    action_index_list.append(plan_key)

        raw = pd.DataFrame.from_dict(rows, orient='index') if rows else pd.DataFrame()
        if raw.empty:
            return action_index_list, raw, raw.copy()
        
        ranked = raw.rank(method='average', ascending=False).fillna(1.0)
        norm = (len(raw) - ranked) / max(1, (len(raw) - 1))
        
        # 将 raw 和 norm 直接存储到每个 plan 中
        for plan_key in rows.keys():
            plan = data_mgr.plan_manager.get(plan_key)
            if plan is not None:
                plan['raw'] = rows[plan_key]
                plan['norm'] = norm.loc[plan_key].to_dict()
                data_mgr.plan_manager.put(plan_key, plan)
        
        return action_index_list, raw, norm
    
    def evaluate_plan(self, plan: Dict) -> Dict[str, float]:
        """评估单个 ActionPlan（基于其 pre_gamestate）
        
        Args:
            plan: ActionPlan 数据
        
        Returns:
            价值评分字典，如 {'man_greedy': 0.5, 'game_lt': 0.3, ...}
            如果无法评估返回 None
        """
        # 先检查 plan 是否已经有评估结果（在 plan_manager 中）
        parent = plan.get('parent', {})
        plan_key = parent.get('plan_key')
        
        if plan_key:
            data_mgr = self.summarizer.dm
            cached_plan = data_mgr.plan_manager.get(plan_key)
            if cached_plan and cached_plan.get('raw'):
                # 如果已有评估结果，直接返回
                return cached_plan['raw']
        
        # 从 parent 中获取 plan 的前后状态
        pre_state_key = parent.get('pre_gamestate')
        post_state_key = parent.get('post_gamestate')
        target_key = parent.get('target_key')
        
        if not all([pre_state_key, post_state_key, target_key]):
            return None
        
        # 从管理器获取数据
        data_mgr = self.summarizer.dm
        pre_state = data_mgr.gamestate_manager.get(pre_state_key)
        post_state = data_mgr.gamestate_manager.get(post_state_key)
        target = data_mgr.target_manager.get(target_key)
        
        if not all([pre_state, post_state, target]):
            return None
        
        # 调用静态方法计算价值
        return self.evaluate_single_plan(pre_state, target, plan, post_state)
    
    @staticmethod
    def evaluate_single_plan(pre_state: Dict, target: Dict, plan: Dict, post_state: Dict) -> Dict[str, float]:
        """计算单个 ActionPlan 的价值评分（静态方法）
        
        Args:
            pre_state: 前状态摘要
            target: TargetInteraction 摘要
            plan: ActionPlan 数据
            post_state: 后状态摘要
        
        Returns:
            价值评分字典，如 {'man_greedy': 0.5, 'game_lt': 0.3, ...}
        """
        from state_analyzer import StateAnalyzer
        
        info = {}
        parent = plan.get('parent', {})
        plan_idx = parent.get('plan_idx', 1)
        
        for dist_metric in ['man', 'game', 'bound', 'com']:
            d_before = pre_state['dist'].get(dist_metric, [float('inf')] * len(StateAnalyzer.PROP_KEYS))
            d_after = post_state['dist'].get(dist_metric, [float('inf')] * len(StateAnalyzer.PROP_KEYS))

            # 1. greedy for win (reach more is better)
            info[f'{dist_metric}_greedy'] = 0.9**d_after[1] - 0.9**d_before[1]
        
            # 2. general for all props (more after is better)
            info[f'{dist_metric}_lt'] = sum(0.9**a - 0.9**b for a, b in zip(d_after, d_before))

        # 3. curious for changes (more interactions after is better)
        info['rules'] = 1 - jaccard_similarity(pre_state['info']['rules'], post_state['info']['rules'])
        info['inters'] = len(post_state['inter']) - len(pre_state['inter'])

        # 4. laziness or randomness
        info['random'] = 0
        info['dist'] = -target['trans'].get('dist', float('inf')) 
        info['repeat'] = 0.9 ** int(plan_idx)

        return info
    
    # ========== 向后兼容 ==========
    
    def describe_action_space(self, grid: 'State') -> Tuple[pd.DataFrame, pd.DataFrame]:
        """[向后兼容] 委托给 evaluate_plan_space，只返回 raw 和 norm"""
        action_index_list, raw, norm = self.evaluate_plan_space(grid)
        return raw, norm
    
    @staticmethod
    def describe_single_action(pre_state: Dict, interact: Dict, post_state: Dict, action_idx: int) -> Dict[str, float]:
        """[向后兼容] 委托给 evaluate_single_plan
        
        注意：这个方法签名与新的 evaluate_single_plan 不完全兼容
        需要将 interact 视为 target，并构造伪 plan
        """
        fake_plan = {
            'plan_idx': action_idx,
            'target_key': interact.get('target_key', ''),
            'post_gamestate': list(interact.get('trans', {}).get('post_gamestates', {}).values())[0] 
                              if interact.get('trans', {}).get('post_gamestates') else None
        }
        return PlanValueEvaluator.evaluate_single_plan(pre_state, interact, fake_plan, post_state)
