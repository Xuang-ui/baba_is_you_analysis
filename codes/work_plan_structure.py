
from typing import TYPE_CHECKING, Optional
from state_storage import get_data_manager
from recorder import Gridmap
import gc
from mdpframework import Environment
import sys


# ====== data preparation ======
ALLMAP = ['intro', 'tutorial', 'base', 'target', 'maze', 'make', 'break', 'helper']
def get_plan_structure(env: 'Environment', map_name: Optional[str] = None, dm_root = 'recording') -> dict:
    if map_name is None or map_name not in ALLMAP:
        for map in ALLMAP:
            get_plan_structure(env, map)
        return
    from state_storage import get_data_manager
    from plan_hierachy import PlanBuilder
    dm = get_data_manager(f'{dm_root}/{map_name}')
    _, state_init = env.mm(map_name)
    pb = PlanBuilder(state_init)
    print(f'\nStart building plan structure for map {map_name}, to deal is {len(env.em(map_name))} subjects.')
    cumulated_subject = 0
    for uid, data in env.em(map_name).items():
        if uid >= 0:
            try:
                plan, states = pb.build_plan(data.Action)
                # plan.create(int(uid))
                data['Grid'] = states
                data['Hierachy'] = plan.coding()
            except Exception as e:
                print(f"Error processing UID {uid} in map {map_name}: {e}")
                continue
            cumulated_subject += 1

        if cumulated_subject % 100 == 0: 
            print(cumulated_subject, end = ', ')
            dm.save_all()

    dm.save_all()

def get_post_grid(env, map_name, dm_root):
    from state_storage import get_data_manager
    from plan_hierachy import PlanBuilder
    dm = get_data_manager(f'{dm_root}/{map_name}')
    _, state_init = env.mm(map_name)
    pb = PlanBuilder(state_init)
    print(f'\nStart building plan structure for map {map_name}, to deal is {len(env.em(map_name))} subjects.')
    cumulated_subject = 0
    for uid, data in env.em(map_name).items():
        if uid >= 0:
            try:
                states = pb.iter_action_sequence(data.Action)
                # plan.create(int(uid))
                data['Grid'] = states
            except Exception as e:
                print(f"Error processing UID {uid} in map {map_name}: {e}")
                continue
            cumulated_subject += 1

        if cumulated_subject % 100 == 0: 
            print(cumulated_subject, end = ', ')




if __name__ == "__main__":
    env = Environment(Gridmap)
    ALLMAP = ['intro', 'tutorial', 'base', 'target', 'maze', 'make', 'break', 'helper']
    cols = ['Count', 'Action', 'Before', 'After', 
        'pred_maximum','pred_weighted','pred_state_0','pred_state_1','pred_state_2','pred_state_3']
    env.init_experience('game_action_rt_with_hmm_pred.csv', cols)
    map_name = sys.argv[1] if len(sys.argv) > 1 else 'intro'
    get_plan_structure(env, map_name, dm_root='../recording')
    env.em.save_exp_file(cover=True)


    