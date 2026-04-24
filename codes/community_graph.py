"""社区图相关类 - CoordSet, Community, CommunityGraph

用于分析游戏地图中的连通分量和社区结构。
"""

from typing import TYPE_CHECKING, Set, Dict, List, Tuple
from collections import defaultdict
from itertools import combinations
from util import Deque, PriorityQueue

if TYPE_CHECKING:
    from recorder import State
    from base_gameLogic import Coord, Tile


class CoordSet:
    """坐标集合类，支持邻居扩展和曼哈顿距离计算"""
    
    def __init__(self, coords):
        self.coords = set(coords)
    
    def is_empty(self):
        return len(self.coords) == 0
    
    def get_coords(self):
        return self.coords.copy()
    
    def __len__(self):
        return len(self.coords)
    
    def neighbors(self):
        """返回所有坐标及其邻居的 CoordSet"""
        neighbors = self.get_coords()
        for coord in self.coords:
            neighbors.update(coord.neighbors)
        return CoordSet(neighbors)
    
    def intercept(self, other):
        """返回与另一个 CoordSet 的交集"""
        assert hasattr(other, 'coords')
        return self.coords.intersection(other.coords)
    
    def manhattan(self, other):
        """计算到另一个 CoordSet 的曼哈顿距离"""
        distant, now = 0, self
        while not now.intercept(other):
            distant += 1
            now = now.neighbors()
        return distant
    
    def centroids(self):
        """计算质心坐标"""
        x_sum, y_sum = 0, 0
        for coord in self.coords:
            x_sum += coord.x
            y_sum += coord.y
        n = len(self.coords)
        return (x_sum / n, y_sum / n)


class Community(CoordSet):
    """社区类，表示连通的同类型 tile 集合"""
    
    def __init__(self, example: 'Tile'):
        self.identity = example.get_full()
        self.gridmap = example.gridmap
        example.community = self
        self.coords = self._expand(example)
        self.nodes = None
        
    def _expand(self, example: 'Tile') -> Set:
        """从示例 tile 开始 BFS 扩展，找出所有连通的同类型 tile"""
        coord_set, visited, dq = set(), set(), Deque()
        dq.push(example.coord)
        while not dq.isEmpty():
            coord = dq.pop()
            coord_set.add(coord)
            visited.add(coord)
            for neighbor in coord.neighbors:
                if neighbor in visited:
                    continue
                visited.add(neighbor)
                nei_tile = self.gridmap.get_tile(neighbor)
                if nei_tile == example:
                    nei_tile.community = self
                    dq.push(neighbor)

        return coord_set
    
    def get_description(self):
        return f"{self.identity} * {len(self)}"
    
    def empty_com(self):
        """判断是否为空社区"""
        return self.identity == 'Empty'
    
    def cost(self):
        """返回穿越该社区的代价（空社区代价为 0）"""
        return 0 if self.empty_com() else 1

    def __str__(self):
        return self.get_description()
    
    def __repr__(self):
        return self.get_description()


class CommunityGraph:
    """社区图类，构建并分析地图中所有社区之间的关系"""
    
    def __init__(self, gridmap: 'State'):
        self.gridmap = gridmap
        self.initialize()

    def initialize(self):
        """初始化社区图：识别社区、构建邻接表、计算最短路径"""
        self.nodes = self.get_communities()
        self.adj, _ = self.get_adjacency()
        self.dist, self.path = self.get_distance()
    
    def get_community_by_prop(self, prop: str) -> Set:
        """获取具有指定属性的所有社区节点"""
        entities = self.gridmap.get_entities_by_prop(prop)
        return {entity.tile.community.nodes for entity in entities if entity.tile.community}

    def get_communities(self) -> Dict[str, Community]:
        """识别地图中所有的连通社区"""
        all_com, all_visited, nodes = defaultdict(int), set(), {}
        for coord, tile in self.gridmap.iter_tiles():
            if coord in all_visited:
                continue
            new_com = Community(tile)
            coords, id = new_com.get_coords(), new_com.identity
            all_com[id] += 1
            all_visited.update(coords)
            new_com.nodes = f'{id}_{all_com[id]}'
            nodes[new_com.nodes] = new_com
        return nodes
    
    def get_adjacency(self) -> Tuple[Dict, Dict]:
        """构建社区邻接表和曼哈顿距离矩阵"""
        adjacency = defaultdict(list)
        manhattan = defaultdict(dict)
        for com1, com2 in combinations(self.nodes.values(), 2):

            man_dist = com1.manhattan(com2)
            manhattan[com1.nodes][com2.nodes] = man_dist
            manhattan[com2.nodes][com1.nodes] = man_dist

            if man_dist == 1:
                adjacency[com1.nodes].append(com2.nodes)
                adjacency[com2.nodes].append(com1.nodes)
        
        return adjacency, manhattan

    def get_distance(self) -> Tuple[Dict, Dict]:
        """计算所有社区之间的最短路径"""
        dist, path = defaultdict(dict), defaultdict(dict)
        for id, com in self.nodes.items():
            dist[id], path[id] = self.get_distance_and_path(com)
        return dist, path
    
    def get_distance_and_path(self, com1: Community) -> Tuple[Dict, Dict]:
        """使用 Dijkstra 算法计算从指定社区到所有其他社区的最短路径"""
        dist = {node: float('inf') for node in self.nodes.keys()}
        parent = {node: None for node in self.nodes.keys()}
        all_path = {node: [] for node in self.nodes.keys()}

        pq = PriorityQueue()
        pq.push(com1.nodes, 0)
        visited = set()
        dist[com1.nodes] = 0

        while not pq.isEmpty():
            cur_id = pq.pop()
            if cur_id in visited:
                continue
            visited.add(cur_id)

            for neighbor in self.adj[cur_id]:
                if neighbor in visited:
                    continue
                weight = self.nodes[neighbor].cost()
                new_dist = dist[cur_id] + weight

                if new_dist < dist[neighbor]:
                    dist[neighbor] = new_dist
                    parent[neighbor] = [cur_id]
                    pq.push(neighbor, new_dist)

                elif new_dist == dist[neighbor]:
                    parent[neighbor].append(cur_id)
        
        def dfs(cur, path, end):
            """DFS 回溯所有最短路径"""
            if cur == com1.nodes:
                all_path[end].append(path[::-1])
                return
            for pred in parent[cur]:
                if pred not in path:
                    dfs(pred, path + [pred], end)

        for com in self.nodes.keys():
            if dist[com] != float('inf'):
                dfs(com, [com], com)

        return dist, all_path
