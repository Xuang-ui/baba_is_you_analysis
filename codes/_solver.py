from codes.base_gameLogic import Action
from codes.base_entity import Coord
from util import PriorityQueue

# ====== Abstract Level ======
class Problem:
    def getStartState(self):
        return 

    def isGoalState(self, state):
        return

    def getSuccessors(self, state):
        return

    def getCostOfActions(self, actions):
        return

class Agent:
    def __init__(self, problem, heuristic):
        self.problem = problem
        self.heuristic = heuristic
        self.actions = None
        self.cost = None

    def register(self):
        self.actions, self.cost = aStarSearch(self.problem, self.heuristic)

    def getAction(self):
        if self.actions is None:
            self.register()
        if self.actions is None:
            return None, self.cost
        return self.actions, self.cost

def aStarSearch(problem, heuristic):

    pq = PriorityQueue()
    pq.push((problem.getStartState(), [], 0), 0)
    visited = set()

    while not pq.isEmpty():
        (current_state, path, past_cost) = pq.pop()

        if current_state in visited:
            continue
        visited.add(current_state)
        if isinstance(problem, PushToProblem):
            print(current_state, path, past_cost)

        # if past_cost > 1000:
        #     return [], 1000

        if problem.isGoalState(current_state):
            return path, past_cost
        


        for (successor, action, cost) in problem.getSuccessors(current_state):
            if successor is not None and successor not in visited:
                g_cost = past_cost + cost
                # 传递路径给heuristic，让它计算动作变化惩罚
                f_cost = heuristic(successor, problem, path + [action]) + g_cost
                pq.update((successor, path + [action], g_cost), f_cost)
    return [], 100

def nullHeuristic(state, problem, path=None):
    return 0

# ====== MoveTo Problem ======

class MoveToProblem(Problem):
    
    def __init__(self, start, goal, grid):
        self.startState = start
        self.goalState = goal
        self.empty = {*grid.get_empty_coords(), start, goal}
        self.push = {entity.get_coord() for entity in grid.get_entities_by_prop('Push')}
        self._expanded = 0

    def getStartState(self):
        return self.startState

    def isGoalState(self, state):
        return state == self.goalState
    
    def getSuccessors(self, state):
        self._expanded += 1
        for next_action in [Action.up, Action.down, Action.left, Action.right]:
            next_state = next_action.get_neighbor_coord(state)
            if next_state is not None:
                yield (next_state, next_action, self.getCost(next_state))

    def getCost(self, next_state):
        return 1 if next_state in self.empty else 1000


def MoveToHeuristic(state, problem, path=None):
    goal = problem.goalState
    man_dist = state.manhattan(goal)
    if len(path) >= 2 and path[-1] != path[-2]:
        man_dist += 2
    return man_dist

def MoveTo(start, goal, grid):
    if goal is None:
        return None, 10000
    problem = MoveToProblem(start, goal, grid)
    agent = Agent(problem, MoveToHeuristic)
    return agent.getAction()


# ====== Push Problem ======
class PushToProblem(MoveToProblem):

    def __init__(self, start, target, goal, grid):
        # 状态: (agent_position, target_position)
        self.startState = (start, target)
        self.goalState = goal
        self.grid = grid
        self.empty = {*grid.get_empty_coords(), start, goal}
        self.push = {entity.get_coord() for entity in grid.get_entities_by_prop('Push')}
        self.stop = {entity.get_coord() for entity in grid.get_entities_by_prop('Stop')}
        self._expanded = 0
        self.info = {}
    
    def isGoalState(self, state):
        # 目标：target到达goal位置
        return state[1] == self.goalState
    
    def getSuccessors(self, state):
        self._expanded += 1
        for next_action in [Action.up, Action.down, Action.left, Action.right]:
            next_state = (state[1], next_action.get_neighbor_coord(state[1]))
            if next_state[1] is None:
                continue
            self.empty.add(next_state[1])
            cost = self.getCost(state, next_action, next_state)
            yield (next_state, next_action, cost)
        
    def getCost(self, state, action, next_state):
        if next_state[1] in self.empty:
            cost1 = 0
        elif next_state[1] in self.stop:
            cost1 = 1000
        elif next_state[1] in self.push:
            cost1 = 10
        else:
            cost1 = 100
        _, cost2 = Push(state[0], state[1], action, self.grid)
        return cost1 + cost2

def PushToHeuristic(state, problem, path=None):
    goal = problem.goalState
    man_dist = state[1].manhattan(goal)
    if len(path) >= 2 and path[-1] != path[-2]:
        man_dist += 1
    return man_dist * 10

def Push(start, target, action, grid):
    inter = action.reverse().get_neighbor_coord(target)
    action1, cost1 = MoveTo(start, inter, grid)
    if action1 is None:
        return None, cost1
    colli = 0 if start == inter or inter in grid.get_empty_coords() else 999
    action2, cost2 = MoveTo(inter, target, grid)
    # print(start, target, action, action1 + action2, cost1 + cost2 + colli)
    return action1 + action2, cost1 + cost2 + colli

def PushTo(start, target, goal, grid):
    problem = PushToProblem(start, target, goal, grid)
    agent = Agent(problem, PushToHeuristic)
    push_trace, cost = agent.getAction()
    if push_trace is None:
        return None, cost

    sequence = []
    for action in push_trace:
        sequence += Push(start, target, action, grid)[0]
        start, target = target, action.get_neighbor_coord(target)
    return sequence, cost


# ====== Real World Function======

def select_park_goal(target, grid): 
    visited = {}
    queue = [target]
    while queue:
        state = queue.pop(0)
        if state in visited:
            continue
        visited[state] = True
        for neighbor in state.neighbors:
            if neighbor in visited:
                continue
            if count_empty(neighbor, grid) == 5:
                return neighbor
            queue.append(neighbor)
    return None

def count_empty(coord, grid):
    count = int(grid.get_tile(coord).is_empty())
    for neighbor in coord.neighbors:
        if neighbor and grid.get_tile(neighbor).is_empty():
            count += 1
    print(coord, count)
    return count


def interaction(obj1, obj2, grid):
    action, cost = None, float('inf')
    if obj2.has_prop('You'):
        obj1, obj2 = obj2, obj1
    if obj1.has_prop('You'):
        if obj2.has_prop('Win'):
            action = 'MoveTowardsWin'
            seq, cost =  MoveTo(obj1.get_coord(), obj2.get_coord(), grid)
        if obj2.has_prop('Push'):
            target = select_park_goal(obj2.get_coord(), grid)
            action = f'Park {obj2.get_coord()} at {target}'
            seq, cost = PushTo(obj1.get_coord(), obj2.get_coord(), target, grid)


    if action is None: 
        return 'undifined'
    return f'{action}\n{seq}\ncost: {cost} {"(Not recommended)" if cost > 100 else "(Recommended)"}'