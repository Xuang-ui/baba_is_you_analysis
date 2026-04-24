from recorder import State, Trans, StateKey, TransKey
from base_gameLogic import Action
from util import decoding, encoding
from typing import ClassVar, Optional, List, TYPE_CHECKING, Dict, Any
from state_storage import get_data_manager
from trans_analyzer import PUSH_CHAIN_COMPARE_BY, PushChain

if TYPE_CHECKING:
    from recorder import State, Trans

RESTART, END, UNDO = 'RESTART', 'END', 'UNDO'

    #    identity = {i: tuple(e[0] for e in t) for i, t in chain.items()}
    #     texture = {i: tuple(e[1] for e in t) for i, t in chain.items()}
    #     prop = {i: tuple(str(e[2]) for e in t) for i, t in chain.items()}
    #     return {'id_chain': identity, 'texture_chain': texture, 'prop_chain': prop}

class PlanKey(str):

    @staticmethod
    def from_plan(plan: 'HierachyAction') -> 'PlanKey':
        key_str = f"{plan.name}_{plan.pre_state.key}_{encoding(plan.identity)}"
        return PlanKey(key_str)

    @staticmethod
    def from_components(name: str, pre_state_key: StateKey, identity: tuple) -> 'PlanKey':
        key_str = f"{name}_{pre_state_key}_{encoding(identity)}"
        return PlanKey(key_str)


class PlanBuilder:

    def __init__(self, init_state: State):
        if not isinstance(init_state, State):
            init_state = State(init_state)
        self.init_state_key = init_state.key
        self.full_plan = NewPlanFull(self.init_state)

    @property
    def init_state(self) -> State:
        return State(key=self.init_state_key)
    
    def reset(self):
        self.full_plan = NewPlanFull(self.init_state)
        return self.init_state, self.full_plan
    
    def parse_action_sequence(self, action_seq: List[Any]) -> List[Action]:
        """ 给定文本列表，识别出对应的 Action 实例列表 """
        return [Action.from_char(item) for item in action_seq]
    
    def quick_build_unit(self, action_seq: List[Any]) -> 'NewPlanUnit':
        """ 给定动作序列，快速生成对应的 NewPlanUnit 实例 """
        state, _ = self.reset()
        try:
            plan = NewPlanUnit(state)
            for action in self.parse_action_sequence(action_seq):
                trans = state.to_trans(action)
                state = trans.to_state()
                plan.add_unit_force(trans.to_plan())
            plan.sealed = True
        except Exception as e:
            print(f"Error for {self.init_state_key}: {''.join([a for a in action_seq])}")
        return self.build_plan(action_seq, thinning=True)[0]
    
    def iter_action_sequence(self, action_seq: List[Any]) -> List[Action]:

        state, _ = self.reset()
        state_stack = [self.init_state_key]
        trans_list = []
        for action in self.parse_action_sequence(action_seq):

            if action.is_undo():
                if len(state_stack) > 1:
                    state_stack.pop()
                next_state = State(key=state_stack[-1])
                trans = state.to_trans(action, next_state)

            elif action.is_restart():
                state_stack = [self.init_state_key]
                next_state = self.init_state
                trans = state.to_trans(action, next_state)
            
            else:
                trans = state.to_trans(action)
                next_state = trans.to_state()
                state_stack.append(next_state.key)

            trans_list.append(next_state)
            state = next_state
        
        return trans_list
    
    def build_plan(self, action_seq: List[Any], thinning = False) -> 'HierachyAction':
        """ 给定动作序列，生成对应的 Plan 实例 """
        state, plan = self.reset()
        state_stack = [self.init_state_key]
        trans_list = []

        for action in self.parse_action_sequence(action_seq):


            if action.is_undo():
                if len(state_stack) > 1:
                    state_stack.pop()
                next_state = State(key=state_stack[-1])
                trans = state.to_trans(action, next_state)
            
            elif action.is_restart():
                state_stack = [self.init_state_key]
                next_state = self.init_state
                trans = state.to_trans(action, next_state)
            
            else:
                trans = state.to_trans(action)
                next_state = trans.to_state()
                state_stack.append(next_state.key)

            trans_list.append(next_state)
            plan.step_in(trans.to_plan())
            state = next_state
        
        plan.closing()
        
        if thinning:
            plan = plan.thinning()

        return plan.save(), trans_list

        

class HierachyAction:
    supplan_unit, subplan_unit = None, None
    abstract_level: int = None
    sealed: bool = False

    def save(self) -> 'Plan':
        for subplan in self.subplans:
            if subplan.abstract_level > 1:
                subplan.save()
        return Plan(self)
    
    def __init__(self, pre_state: State, subplans: List['HierachyAction'] = None):

        self.pre_state: State = pre_state
        self.supplan: Optional['HierachyAction'] = None
        self.supidx: int = None
        self.subplans: List['HierachyAction'] = []
        for subplan in subplans or []:
            self.add_unit_force(subplan)
        self.feature = PUSH_CHAIN_COMPARE_BY
    
    def set_feature(self, feature: str):
        self.feature = feature

    @property
    def name(self) -> str:
        return self.__class__.__name__[7:]
    
    # ====== 基本构筑单元 =======

    @property
    def post_state(self) -> State:
        return self.get_last_subplan().post_state if not self.is_empty() else self.pre_state
    
    @property
    def chain(self) -> PushChain:
        return self.get_last_subplan().chain if not self.is_empty() else PushChain({})
    
    @property
    def action(self) -> Action:
        return self.get_last_subplan().action if not self.is_empty() else Action.login
    
    @property
    def identity(self) -> tuple:
        return [item for sub in self.subplans for item in sub.identity]
        
    def is_empty(self) -> bool:
        return len(self.subplans) == 0
    
    def is_single(self) -> bool:
        return len(self.subplans) == 1
    
    def get_supplan(self) -> 'HierachyAction':
        return self.supplan if self.supplan else self.build_supplan()
    
    def build_supplan(self) -> 'HierachyAction':
        return self.supplan_unit(self.pre_state, [self]) if self.supplan_unit else None
    
    def get_last_subplan(self) -> 'HierachyAction':
        return self.subplans[-1] if not self.is_empty() else self.build_last_subplan()

    def build_last_subplan(self) -> 'HierachyAction':
        to_build = self.subplan_unit(self.pre_state)
        self.add_unit_force(to_build)
        return to_build
    
    # ====== 构筑方法 =======
    def step_in(self, subplan: 'HierachyAction') -> bool:
        assert subplan.pre_state == self.post_state, 'Wrong pre_state'
        assert self.abstract_level > subplan.abstract_level, 'Wrong abstract_level'

        if isinstance(subplan, self.subplan_unit):
            self.add_unit(subplan)  # 恰好比 subplan 高一级

        else:
            self.get_last_subplan().step_in(subplan)  # 递归从子节点加入
    
    def add_unit(self, subplan: 'HierachyAction'):
        assert subplan.pre_state == self.post_state, 'Wrong pre_state'
        assert isinstance(subplan, self.subplan_unit), 'Wrong subplan type'

        to_check, to_add = subplan, self
        while True:
            if to_add.add_unit_direct(to_check):
                break # 成功加入
            # 递归向上尝试加入
            to_check, to_add = to_check.build_supplan(), to_add.get_supplan()

    def add_unit_direct(self, subplan: 'HierachyAction') -> bool:
        assert subplan.pre_state == self.post_state, 'Wrong pre_state'
        assert isinstance(subplan, self.subplan_unit), 'Wrong subplan type'

        if not subplan.sealed or self.compatible(subplan):
            # 晚封闭的Greedy添加
            self.add_unit_force(subplan)
            return True
        
        # 添加失败的递归向上检查
        self.sealing()
        return False
    
    def add_unit_force(self, subplan: 'HierachyAction'):
        assert subplan.pre_state == self.post_state, 'Wrong pre_state'
        assert isinstance(subplan, self.subplan_unit), 'Wrong subplan type'
        assert self.is_empty() or not subplan.sealed or self.compatible(subplan), 'Incompatible subplan'

        subplan.supplan = self
        subplan.supidx = len(self.subplans)
        self.subplans.append(subplan)

    def check_compatity(self):
        if len(self.subplans) <= 1: return
        self.add_unit(self.subplans.pop())
    
    def compatible(self, subplan: 'HierachyAction') -> bool:
        pass

    def sealing(self):

        if self.sealed: return

        self.sealed = True

        if self.supplan is not None:
            self.supplan.check_compatity()

    def closing(self):
        active_node = self
        while not active_node.is_empty():
            active_node = active_node.get_last_subplan()
        
        while active_node.supplan is not None:
            active_node.sealing()
            active_node = active_node.supplan

    
    def thinning(self) -> 'HierachyAction':
        to_check = self
        while len(to_check.subplans) == 1 and to_check.subplan_unit is not NewPlanStep:
            to_check = to_check.get_last_subplan()
        return to_check
    
    def fatting(self) -> 'HierachyAction':
        to_check = self
        while to_check.supplan_unit is not None:
            to_check = to_check.build_supplan()
        return to_check

    # ====== 可视化与描述 =======
    def get_description(self, order = 0) -> str:

        children = [subplan.get_description(order + 1) for subplan in self.subplans]
        if not children:
            return self.name + "[]"
        if sum(len(c) for c in children) > 50:
            joiner = ",\n" + "  "*(order+1)
            return self.name + "[" + joiner[1:] + joiner.join(children) + joiner[1:] + "]"
        return f"{self.name}[{'->'.join(children)}]"
    
    def str(self):
        return self.get_description()
    
    def __repr__(self):
        return self.get_description()
    
    # ====== 具体层级实现 =======
    def iter_subplans(self, abstract_level: int):
        """返回 plan sequence 中指定抽象层级的所有 subplan"""
        abstract_level = abstract_level
        if self.abstract_level == abstract_level:
            yield self
            return 
        for subplan in self.subplans:
            yield from subplan.iter_subplans(abstract_level)
    
    def iter_step(self):
        yield from self.iter_subplans(1)

    def iter_unit(self):
        yield from self.iter_subplans(2)

class NewPlanStep(HierachyAction):
    abstract_level = 1
    sealed = True
    def __init__(self, pre_state: State, trans: Trans):
        self.pre_state: State = pre_state
        self.supplan: Optional['HierachyAction'] = None
        self.supidx: int = None
        self.subplans: List['HierachyAction'] = []
        self.feature = PUSH_CHAIN_COMPARE_BY
        self.attach: Trans = trans
        # self.sealed = self.is_special() or not self.chain.is_empty()
    
    @property 
    def post_state(self) -> State: return self.attach.to_state()
    @property
    def chain(self) -> PushChain: return PushChain(self.attach['push_chain'])
    @property
    def action(self) -> Action: return self.attach.action
    @property
    def identity(self) -> tuple: return self.chain._collision
    @property
    def action_cost(self) -> int: return self.attach['action_cost']
    @property
    def plan_cost(self) -> int: return self.attach['plan_cost']
    
    def get_description(self, order=0):
        return self.attach.action.value

class NewPlanUnit(HierachyAction):
    abstract_level = 2
    subplan_unit = NewPlanStep

    def compatible(self, subplan: 'NewPlanStep') -> bool:
        return self.chain.is_empty() and not self.action.is_special() # and not subplan.action.is_special()

class NewPlanChunk(HierachyAction):
    abstract_level = 3
    subplan_unit = NewPlanUnit

    def compatible(self, subplan: 'NewPlanUnit') -> bool:
        if self.action.is_special() or subplan.action.is_special():
            return self.action == subplan.action
        return self.chain == subplan.chain

class NewPlanSeq(HierachyAction):
    abstract_level = 4
    subplan_unit = NewPlanChunk

    def compatible(self, subplan: 'NewPlanChunk') -> bool:
        if self.is_empty(): return True
        if self.action.is_special(): return False
        if subplan.action.is_special(): return True
        return self.chain <= subplan.chain   # or subplan.chain <= self.chain

class NewPlanSubgoal(HierachyAction):
    abstract_level = 5
    subplan_unit = NewPlanSeq

    def compatible(self, subplan: 'NewPlanSeq') -> bool:
        if self.action.is_special(): return False
        if subplan.action.is_special(): return False
        return self.chain & subplan.chain

class NewPlanFull(HierachyAction):
    abstract_level = 6
    subplan_unit = NewPlanSubgoal

    def compatible(self, subplan: 'NewPlanSubgoal') -> bool:
        return True

NewPlanStep.supplan_unit = NewPlanUnit
NewPlanUnit.supplan_unit = NewPlanChunk
NewPlanChunk.supplan_unit = NewPlanSeq
NewPlanSeq.supplan_unit = NewPlanSubgoal
NewPlanSubgoal.supplan_unit = NewPlanFull


class Plan:

    @classmethod
    def iter(cls, plan_key: 'PlanKey', level = 'Unit') -> 'Plan':
        current = get_data_manager().get_plan(plan_key)
        if current['level'] == level:
            yield current
        else:
            for sub in decoding(current['subplans']).values():
                yield from cls.iter(sub, level)

    def show(self):
        from state_graphic import Graphic
        g = Graphic(self.plan.pre_state)
        lst = self['identity']
        g.add_path(lst, (255, 0, 0), (255, 255, 0))
        return g()

    def __init__(self, newPlan: 'HierachyAction' = None):

        self.plan = newPlan
        self.key = PlanKey.from_plan(newPlan)
        self.manager = get_data_manager().plan_manager

        if newPlan.abstract_level > 2:
            for sub in newPlan.subplans:
                Plan(sub)
        
        self.describe(False)

    def create(self, id: tuple):
        self.manager[id] = self.key
    
    def coding(self) -> str:
        def get_hierachy(plan, path=''):
            if plan.is_empty():
                return [path]
            results = []
            for sub in plan.subplans:
                new_path = path + ',' + str(sub.supidx) if path else str(sub.supidx)
                results.extend(get_hierachy(sub, new_path))
            return results
        return get_hierachy(self.plan)

    @property
    def analyzer(self) -> 'PlanAnalyzer':
        return PlanAnalyzer(self.plan)
    
    def describe(self, explain: bool = True) -> Dict[str, Any]:
        if self.key not in self.manager:
            summary = self.analyzer.sum_basic_features()
            summary['key'] = self.key
            summarize = {k: encoding(v) for k, v in summary.items()}
            self.manager[self.key] = summarize

        raw_result = self.manager[self.key]
        if not explain: 
            return raw_result
        return {k: decoding(v) for k, v in raw_result.items()}

    def expand(self, method: str) -> Any:
        description = self.describe(False)
        if method not in description:
            if hasattr(self.analyzer, f'get_{method}'):
                answer = getattr(self.analyzer, f'get_{method}')()
                if answer is not None:
                    self.manager[self.key][method] = encoding(answer)
                    return answer
            else:
                raise KeyError(f"Method {method} not found in PlanAnalyzer.")
        return decoding(self.describe(False)[method])
    
    def __getitem__(self, name: str) -> Any:
        return self.expand(name)
    
    def __repr__(self):
        return repr(self.plan)
    
    def to_state(self):
        return State.from_key(self['post_state'])


class PlanAnalyzer:

    def __init__(self, plan: 'HierachyAction'):
        self.plan = plan
        self.pre = plan.pre_state
        self.dm = get_data_manager()

    
    def get_action_cost(self) -> int:
        if self.plan.abstract_level == 2:
            if self.plan.action.is_special():
                return 1
            self.pre.expand('units')
            return None
        return sum(Plan(sub)['action_cost'] for sub in self.plan.iter_unit())
    
    def get_plan_cost(self) -> int:
        return sum(int(subplan.attach['plan_cost']) for subplan in self.plan.iter_step())
    
    def get_subplans(self) -> List[str]:
        
        if self.plan.abstract_level > 2:
            return {subplan.supidx: PlanKey.from_plan(subplan) for subplan in self.plan.subplans}
        elif self.plan.abstract_level == 2:
            return self.plan.identity[0] if self.plan.identity else []  # 单步计划的 identity 即为其 key
        else: return self.plan.action.value

    # ====== 待迁移功能 =======
    def sum_basic_features(self) -> Dict[str, Any]:
        features = {
            'level': self.plan.name,
            'pre_state': self.plan.pre_state.key,
            'post_state': self.plan.post_state.key,
            'identity': self.plan.identity,
            'subplans': self.get_subplans(),
            # 'fake_state': self.fake_state.key,
            # 'plan_costs': self.get_plan_cost(),
        }
        return features
