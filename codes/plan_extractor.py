from plan_hierachy import *
from mdpframework import MapManager, ExperienceManager
from typing import Any
from base_gameLogic import Action
from state_storage import get_data_manager
import pandas as pd

if TYPE_CHECKING:
    from recorder import State
    from pandas import DataFrame as dataframe




class PlanExtractor:
    ACTIONCHECK = {'up': 'w', 'down': 's', 'left': 'a', 'right': 'd', 
                   '↑': 'w', '↓': 's', '←': 'a', '→': 'd',
                   'restart': 'r', 'undo': 'z', '↻': 'r', '↶': 'z'}

    def __init__(self, feature = 'id_chain', map_name: str = None):


        self.mm = MapManager()
        self.em = None
        self.feature = feature
        self.map_name = map_name or 'tutorial'
        self.dm = self.configure_data_manager()
        self.record = {}

    def configure_data_manager(self):
        return get_data_manager()

    def set_experience_file(self, file_name: str):
        self.em = ExperienceManager(file_name)

    def extract_one_subject_plan(self, uid: int, map_name: str = None, experience_df: 'dataframe' = None) -> HierachyAction:
        map_name = map_name or self.map_name

        experience_df = experience_df or self.em(map_name)
        data = experience_df[experience_df['Uid'] == uid]
        action_seq = data['Action'].tolist()

        plan = self.extract_from_sequence(action_seq, map_name, closing=True)
        plan.record(abstract_level=2) # 记载到 unit level
        return plan
    
    def evaluate_one_subject_plan(self, uid: int, map_name: str = None, experience_df: 'dataframe' = None) -> dict:
        plan = self.extract_one_subject_plan(uid, map_name, experience_df)
        # print(plan)
        units = plan.get_subplans(abstract_level=2)
        raws = []
        for unit in units.values():
            # print(unit)
            if isinstance(unit.chain, str):
                continue
            comp = unit.compare()
            comp['key'] = unit.key
            raws.append(comp)
        df = pd.DataFrame(raws).set_index('key')
        return df
    
    def evaluate_all_subjects_plans(self, map_name: str = None, experience_df: 'dataframe' = None, num_episodes: int = float('inf')) -> dict:

        map_name = map_name or self.map_name
        experience_df = experience_df or self.em(map_name)
        plan_result, plan_evaluation = {}, []

        for uid, data in experience_df.groupby('Uid'):
            save_all_data()
            if uid <= 0 or uid > num_episodes:
                continue
            action_seq = data['Action'].tolist()
            try:
                plan = self.extract_from_sequence(action_seq, map_name, closing=True)
                plan.record(abstract_level=2)
                plan_result[uid] = PlanKey.from_plan(plan)

                units = plan.get_subplans(abstract_level=2)
                for i, unit in enumerate(units.values()):
                    if isinstance(unit.chain, str):
                        continue
                    comp = unit.compare()
                    comp['Uid'] = uid
                    comp['unit_idx'] = i
                    comp['plan_key'] = unit.key
                    plan_evaluation.append(comp)
            except Exception as e:
                print(f"Error processing Uid {uid}: {e}")
        df_all = pd.DataFrame(plan_evaluation)
        return plan_result, df_all

    
    def all_subjects_plans(self, map_name: str = None, experience_df: 'dataframe' = None, num_episodes: int = float('inf')) -> dict:

        map_name = map_name or self.map_name
        experience_df = experience_df or self.em(map_name)
        plan_result = {}

        for uid, data in experience_df.groupby('Uid'):

            if uid <= 0 or uid > num_episodes:
                continue

            action_seq = data['Action'].tolist()
            try:
                plan = self.extract_from_sequence(action_seq, map_name, closing=True)
                plan.record(abstract_level=2)
                plan_result[uid] = PlanKey.from_plan(plan)

            except Exception as e:
                print(f"Error processing Uid {uid}: {e}")
        return plan_result


    def initialize(self, map_name: str):
        grid, state = self.mm._prepare_map(map_name)
        grid.describe()
        return grid, state
    
    def extract_from_sequence(self, action_seq: List[Any], map_name: str = None, 
                              start_grid: State = None, 
                              closing: bool = False, thinning: bool = False) -> HierachyAction:
        
        """从解析好的动作序列，step-in 生成完整 Plan"""
        if map_name:
            grid, state = self.initialize(map_name)
        elif start_grid:
            grid = start_grid
            state = grid['key']
        else:
            state = self.state
            grid = state.rebuild()

        actions = self.parse_action_sequence(action_seq)
        full_plan = PlanFull(state)

        for action in actions:
            trans = Trans(grid, action, describe=False)
            full_plan.step_in(PlanStep.from_transition(trans, self.feature))
            grid = trans.post_grid
        if closing:
            full_plan.closing()
        if thinning:
            full_plan = full_plan.thinning()
        return full_plan
    
    def parse_action_single(self, item: Any) -> Action:
        """ 给定文本，识别出对应的 Action 实例 """
        if isinstance(item, Action):
            return item
        
        if isinstance(item, str):
            string = self.ACTIONCHECK.get(item.lower(), item)
            return Action(string)
    
    def parse_action_sequence(self, action_seq: List[Any]) -> List[Action]:
        """ 解析动作序列，返回 Action 列表 """
        return [self.parse_action_single(act) for act in action_seq]