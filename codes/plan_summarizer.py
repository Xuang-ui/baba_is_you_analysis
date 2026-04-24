from plan_hierachy import HierachyAction, PlanKey
from plan_extractor import PlanExtractor
from state_storage import get_data_manager
from util import encoding, decoding, jaccard_similarity
import pandas as pd

from typing import Dict, Any, Union

LAMBDA = 0.9

class PlanSummarizer:
    
    def __init__(self, plan: HierachyAction):
        self.plan = plan
        self.dm = get_data_manager()
    
    @property
    def plan_manager(self):
        return self.dm.plan_manager
    
    def compute_hash(self, plan: HierachyAction = None) -> str:
        plan = plan or self.plan
        return PlanKey.from_plan(plan)
    
    def summary(self, item: Union[HierachyAction, str]) -> Dict[str, Any]:
        if isinstance(item, str):
            return self.read_from_manager(item)
        key = self.compute_hash(item)
        if key in self.plan_manager:
            return self.read_from_manager(key)
        return self.calculate_from_analyzer(item)
    
    def read_from_manager(self, plan_key: Union[str, PlanKey]) -> Dict[str, Any]:
        return self.plan_manager.get(plan_key)
    
    def calculate_from_analyzer(self, plan: HierachyAction = None) -> Dict[str, Any]:
        plan = plan or self.plan
        plan_key = self.compute_hash(plan)
        
        summary_dict = {
            'key': plan_key,
            'action_seq': plan.action_seq,
            'subplans': {i:p.key for i, p in enumerate(plan.subplans)},
            'chain': plan.full_chain(), 
            'abstract_level': plan.name,
            'pre_state': plan_key.pre_state, 
            'post_state': plan_key.post_state,
            'direction': plan_key.direction,
            'evaluation': {**self.compute_action_costs(),**self.evaluate_plan_effects()},
        }

        summarize = {k: encoding(v) for k, v in summary_dict.items()}
        if plan_key not in self.plan_manager:
            self.plan_manager[plan_key] = summarize
        elif len(plan.action_seq) < len(self.plan_manager[plan_key]['action_seq']):
            self.plan_manager[plan_key] = summarize

        return summarize
    
    def compute_action_costs(self) -> Dict[str, Any]:
        return {'action_costs': self.plan.action_costs,
                'plan_costs': self.plan.plan_costs}

    def evaluate_plan_effects(self, plan: HierachyAction = None) -> Dict[str, Any]:
        plan = plan or self.plan
        pre_state, post_state = plan.pre_state, plan.post_state
        fake_state = plan.fake_state
        info = {}

        for dist in ['man_dist', 'game_dist', 'bound_dist', 'com_dist']:
            d_before = pre_state[dist]
            d_after = post_state[dist]
            d_fake = fake_state[dist]

            for prop in d_before.keys():
                info[f'post_{dist}_{prop}'] = LAMBDA**d_after[prop] - LAMBDA**d_before[prop]
                info[f'fake_{dist}_{prop}'] = LAMBDA**d_fake[prop] - LAMBDA**d_before[prop]
            info[f'post_{dist}_delta'] = sum(LAMBDA**v for v in d_after.values()) - sum(LAMBDA**v for v in d_before.values())
            info[f'fake_{dist}_delta'] = sum(LAMBDA**v for v in d_fake.values()) - sum(LAMBDA**v for v in d_before.values())
        info['post_rules'] = 1 - jaccard_similarity(pre_state['rules'], post_state['rules'])
        info['fake_rules'] = 1 - jaccard_similarity(pre_state['rules'], fake_state['rules'])
        total_ent = sum(v[0] for v in pre_state['objects'].values())
        info['post_inters'] = (len(post_state['targets']) - len(pre_state['targets'])) / max(1, total_ent)
        info['fake_inters'] = (len(fake_state['targets']) - len(pre_state['targets'])) / max(1, total_ent)
        return info

    def compare(self, plan: HierachyAction = None) -> dict:
        plan = plan or self.plan
        if isinstance(plan, str):
            return {}
        action_space = [PlanKey(unit) for unit in plan.pre_state['plan_unit']]
        rows = []
        for unit in action_space:
            plan_eva = unit.evaluate()
            plan_eva['key'] = str(unit)
            rows.append(plan_eva)
        raw = pd.DataFrame(rows).set_index('key')
        ranked = raw.rank(method='average', ascending=False).fillna(1.0)
        norm = (len(raw) - ranked) / max(1, (len(raw) - 1))
        my_rank = dict(norm.loc[PlanKey.from_plan(plan)])
        if 'comparison' not in self.plan_manager[plan.key]:
            self.plan_manager[PlanKey.from_plan(plan)]['comparison'] = encoding(my_rank)
        return my_rank