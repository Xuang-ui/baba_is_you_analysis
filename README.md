## 关于baba研究的说明文件

更多对 baba is you 游戏本体的了解，可以参考
- 游戏原作：Arvi “Hempuli” Teikari, 2019
- wiki百科：baba is wiki

# menu
1. 怎么玩这个游戏？
- 直接运行 plan_interactive.py 文件

2. 底层逻辑实现 Python 版本的 Baba is you
- base_entity.py: 基于【Property, Coord, EntityID】三位一体定义 Entity
- base_gameLogit.py: 补充 Action, GameOutcome 后基于 Tile 定义 GameEngine
- base_rule.py: 基于 Token 定义 Rule 和 RuleManager
- texture: 材质包
- ../levels: 关卡存储

3. 游戏状态的分析和存储
- 存储结构和数据类型：recorder.py (数据结构)，state_storage.py (存储结构)
- state_analyzer.py, state_summarizer.py, state_solver.py(目前没用)
- trans_analyzer.py, trans_summarizer.py, target_simulator.py(目前没用)
- plan_hierachy.py, plan_summarizer.py, plan_extractor.py（功能过剩）, plan_value_manager.py(目前没用)
- ../recording: 所有 state, transition 按照关卡存储

4. 真实被试的行为反应
- ../data: 被试的行为反应数据
- model_hmm.py: 反应时数据建模
- work_plan_structure.oy: 动作序列数据建模

## 1.Baba 是一个怎样的游戏 (in process)

## 2.底层逻辑（base）

### 2.1 base_entity
entity = id: material + coord + property
#### 2.1.1 property
**property, 基于 int(flag) 的二进制掩码，记录属性**
1. 可能取值定义在VALIDDICT和VALIDLIST中，有规则定义属性 You, Win, Push, Defeat, STOP 五种，后续可以继续添加，和默认属性 Text, Regular, Empty
2. flag(存储): 二进制整数，所有规则增减计算的底层逻辑
3. prop_lst(展示): 字符串列表 与 Property 示例的转化
4. regular_check: 很微妙的属性，姑且这样实现一下

#### 2.1.2 coord
**coord(tuple), 基于tuple的二维坐标，考虑游戏边界**
1. range: $0<=x<width$, $0<=y<height$
2. 值得说明的是，y=0表示界面最下边(dowm,s)的方向
3. 超出边界的被集中表示为 Boundary 类别

#### 2.1.3 material
**material(str)，给定一个ASCII编码（entity_id）能得到所图案信息**
1. type: 有 noun, object, operater, property 四大基本类别，为了额外功能引入 special(empty,bound,text,regular), attribute(宾语), text(token) 类别，可以实现基本的类型判断和转化；
2. full_name: short_name 用于存储，full_name用于展示；
3. texture：直接索引 texture 文件加中的 png 图像。
4. default_property: 给出没有规则条件下的默认属性 Regular for object, Text for text, Stop for boundary, Empty for empty

#### 2.1.4 entity
**向下封装material, coord, property, 向上对接 tile, gridmap**
1. 初始化中可以平凡的定义 material 和 coord，也可以强制定义 global_id 和 prop(但是目前没必要), 平凡的继承了他们的属性
2. property比较特殊，有默认值，还可以根据gridmap规则自动化提取
3. quick_save(存储): 使用tuple记录全部信息，快照保证后续不被修改
4. get_discription(展示): coord: full_name, property

### 2.2 base_gameLogic

gameEngine 基于 material, coord, property 对 entity 进行组织

#### 2.2.1 tile
**gridmap中相同坐标下entities的集合**
1. gridmap: 初始化格子并绑定在 EntityTile 下
2. entities管理：基本操作有增减移清，同时改变self.entities和gridmap.entities
3. prop管理：union of entities prop, 延迟计算，基于属性的 collision 检测
4. token: 输出str表示可能组成规则的token
5. quick_save(存储): {coord: list to tuple(entity)}
6. get_discription(展示)：coord: content, property

#### 2.2.2 collector
**整个地图下的所有entity可以用material, coord, property来组织**
1. EntityProp基于原子Property(str而不是Property)组织，EntityID基于short_name(str而不是Material)组织，使用懒惰存储加快读取, id_counter分配global_id. 
2. EntityTile基于坐标Coord组织，委托给Tile管理；Rule委托给RuleManager管理
3. entities管理：Coord主导的逐步更新，并标记其他内容dirty延迟更新
4. quick_save(存储): size + list of tuple(entity)
5. get_discription(展示): 字符串坐标格式

#### 2.2.3 gameEngine
**(Collector + GameOutcome) -Action-> (Collector + GameOutcome)**
1. GameOutcome: 4种可能状态，continue下可以活动， win判断胜利，still下没有you, quit退出游戏；Defeat逐渐被淘汰
2. Action: wasd四种常规移动，z是撤销，q是退出，r是重启，space是等待
3. GameHistory: 存储了(Action, Collector) pair
4. step函数，输出永远是Collector, Outcome, Info。
    非前进：z和r都是基于gameHistory重构Collector, q是退出游戏
    前进：move赋予agent移动能力，still剥夺agent移动能力，按照移动-规则-碰撞顺序处理
5. 处理移动：对每一个发起者(move或者you属性的entity)，尝试移动，根据目的地属性（stop：尝试移动失败；push/text：目标作为新的发起者递归尝试移动；other：移动成功），只涉及move_entity的操作，被递归纳入者称为push_chain
6. 处理规则：委托给 RuleManager 进行
7. 处理碰撞: 委托给 EntityTile 进行

### 2.4 base_rule
**RuleManager管理Token->Rule**

#### 2.4.1 Token
**继承自Material，带坐标的Text**
1. 只有 is_text的Material可以转化为token，同时标记 coord 和 rule
2. 完成 noun, property, attribute, operator的判断

#### 2.4.2 Rule
**本质上就是list of token，不同类型规则新的子类中**
1. 维持 rule-token的双向连接
2. noun_is_property: active; noun_is_noun: inactive
3. 原子化的规则只有这两类？baba on keke is win


#### 2.4.3 RuleManager
**两大基本功能：get获取规则，apply应用规则。基于manager进行管理**
1. read: 直接读取rules中不同种类规则存储
2. clear: 清空所有 rules 和 manager
3. detect: clear后基于token_map重新检测规则。
4. get: 基于 gameEngine是否对对text的add,remove和move决定read or detect rules。
5. apply: np-标记所有改为p属性，nn-标记所有n替换为n' material
6. update: get + apply


## 3 状态管理

所有涉及的文件
- state_storage：in-memory 和 json 存储记录的后端
- recorder: Girdmap, State, StateKey, Trans, TransKey 抽象层次漫步
- state_analyzer: 对state的描述分析
- trans_analyzer: 对trans的描述分析
- state graphic: 对state进行可视化



### 3.1 state summary样例
1. 记录Agent位置'you': '[(5,6)]',
2. 记录游戏结果(continue/win/defeat)'outcome': 'Continue',
3. 记录游戏规则Property-Object 'rules': '{YOU:(c);WIN:(d);PUSH:(p);DEFEAT:(s);STOP:();TEXT:();REGULAR:();EMPTY:()}',
4. 组成规则和离散token数量：'tokens': '[(S,0,5)|(C,0,2)|(D,0,3)|(P,0,1)]',
5. Object数量 'objects': '{p:28;s:3;c:1;d:1}',
6. 不同属性物体数量 'prop': '{TEXT:12;PUSH:28;DEFEAT:3;YOU:1;WIN:1;EMPTY:176}',
7. 到不同属性的距离(1)'man_dist': '{YOU:0;WIN:6;PUSH:2;DEFEAT:3;STOP:9999;TEXT:3;REGULAR:9999;EMPTY:1}', (2)'game_dist': '{YOU:0;WIN:9999;PUSH:2;DEFEAT:3;STOP:9999;TEXT:9999;REGULAR:9999;EMPTY:1}',(3)'bound_dist': '{YOU:0;WIN:2;PUSH:1;DEFEAT:1;STOP:9999;TEXT:2;REGULAR:9999;EMPTY:0}',
8. 可以触及的物体和路径'units': '{(5,7,w):ww;(5,5,s):ss;(4,6,a):aa;(4,7,w):waw;(4,7,a):waa;(6,7,w):wdw;(4,5,s):sas;(4,5,a):saa;(6,5,s):sds;(7,6,d):ddd;(7,7,w):wddw;(7,7,d):wddd;(7,5,s):sdds;(7,5,d):sddd}'
以下不作为特征
9. 状态编码 'key': 'S-733f9f61ada581ce',
10. 地图原始数据 'raw': '[(0,S,32,3,3)|(1,0,32,4,3)|(2,5,32,5,3)|(3,D,32,11,3)|(4,0,32,12,3)|(5,3,32,13,3)|(6,p,4,3,4)|(7,p,4,4,4)|(8,p,4,5,4)|(9,p,4,6,4)|(10,p,4,7,4)|(11,p,4,8,4)|(12,p,4,9,4)|(13,p,4,10,4)|(14,p,4,11,4)|(15,p,4,12,4)|(16,p,4,13,4)|(17,p,4,3,5)|(18,s,8,8,5)|(19,p,4,13,5)|(20,p,4,3,6)|(21,c,1,5,6)|(22,s,8,8,6)|(23,d,2,11,6)|(24,p,4,13,6)|(25,p,4,3,7)|(26,s,8,8,7)|(27,p,4,13,7)|(28,p,4,3,8)|(29,p,4,4,8)|(30,p,4,5,8)|(31,p,4,6,8)|(32,p,4,7,8)|(33,p,4,8,8)|(34,p,4,9,8)|(35,p,4,10,8)|(36,p,4,11,8)|(37,p,4,12,8)|(38,p,4,13,8)|(39,C,32,3,9)|(40,0,32,4,9)|(41,2,32,5,9)|(42,P,32,11,9)|(43,0,32,12,9)|(44,1,32,13,9)|(17,13)]',
1. StateKey 是状态"身份证"
2. TransKey 是动作"身份证"

状态特征化与相似度分析的设计思路
基于你的 Baba Is You 状态摘要结构，我提供以下设计思路：
## 4 计划管理
所有涉及的文件
- plan hierachy: 现在PlanKey, PlanBuilder, HierachyAction, Plan, PlanAnalyzer团在一起，可以拆分一下


## 5 数据管理
所有涉及的文件
- mdpframework.py: 只用到Environment, MapManager, ExperimenceManager














## Old Things
### main
1 codes/tkin.py 包含了全部演示功能，python tkin.py 可以进行演示
- 需要安装numpy, tkiner, PIL 三个前置库
- 模式切换：游戏模式，分析模式（解题思路演示），编辑模式
    编辑模式（修改游戏地图）和 游戏模式（游戏引擎模拟）额外参考 game logic 段落
    分析模式（解题思路演示）参考 analysis 段落
    回访模式（玩家数据回放）参考 replay 段落
- 地图以txt格式存储在levels文件夹下
    地图表示规则参考 level 段落
    从 txt 文件导入预存储的待分析地图
    修改后的地图可以保存到 levels 文件夹下
2 codes/inter.py 是基于 ASCII 的粗略模拟，目前已经废弃

### levels
levels中用txt文件存储地图
- reversed y axis: txt中从下到上，对应line0 - line(height-1)
- normal x axis: txt中从左到右，对应row0 - row(weight-1)
- 单个格子(tile)用 ASCII 表示，对应 codes/entity.Entity.entitiy_id attr
    对应规则记录在 codes/entity.EntityType类下
    在 codes/rule.Rule 类下也有使用，todo：下次更新后将会被废弃

使用ASCII编码的entity
- 小写字母表示具体Object，大写字母对应相应Noun for Object
- 数字代表Property
- 0代表IS operator，todo：下次更新将会修改
- entity_id 到 entity_full_name 的映射参考 codes/entity.EntityType

游戏贴图
- 存储在 codes/texture文件夹内. todo:作为单独文件夹
- entity_id 到 entity_texture_path 的映射参考 codes/rule.entity_id_to_texture todo：迁移到entity
- All sprite textures are retrieved from the [MultiPic database](https://www.bcbl.eu/databases/multipic/).

### game logic
游戏序列层级：（property + coord）-> entity -> tile -> (rule + community)gridmap
- entity及以下 codes/entity.py，全部底层操作实现
- tile和gridmap：codes/gridmap.py，实现gridmap.step(action) -> new_gridmap, outcome, info
- rule(特殊的text community)，codes/rule.py
- todo: step函数可以输出发生了哪些object interaction和rule change

### analysis
不同层级的分析：codes/analyzer.py
- Object Community的分析
- todo: 基于rule community专门的分析
- todo: 基于room level的分析

基于分析提供的解题思路：codes/solver.py
- 基本行为 coord 层级：MoveTowards, MoveTo, PushTowards, PushTo
- 现实游戏 entity/tile 层级
- todo: 高阶表征 community/room 层级，的object和抽象 rule 表征
- todo: 任务 level 层级的 algorithm 和 超任务层级的 meta learning
