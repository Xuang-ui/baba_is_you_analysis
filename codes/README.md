## 关于baba研究的说明文件

更多对 baba is you 游戏本体的了解，可以参考
- 游戏原作：Arvi “Hempuli” Teikari, 2019
- wiki百科：baba is wiki

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
