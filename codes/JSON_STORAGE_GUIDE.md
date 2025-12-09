# JSON 存储后端使用指南

## 概述

`state_storage.py` 现在支持两种存储后端：

1. **InMemoryBackend** - 纯内存存储（默认）
2. **JSONBackend** - JSON 文件持久化存储（新增）

两种后端实现相同的 `StorageBackend` 接口，可以无缝切换。

## 快速开始

### 1. 配置 JSON 存储

```python
from state_storage import configure_json_storage, save_all_data

# 配置 JSON 存储（数据保存到 ./data 目录）
gamestate_backend, target_backend, plan_backend = configure_json_storage(
    storage_dir='./data',
    auto_save=True  # 每次修改自动保存
)

# 此后所有的 gamestate_manager, target_manager, plan_manager 都会使用 JSON 存储
```

### 2. 正常使用（与内存后端相同）

```python
from recorder import Gridmap, get_data_manager

# 创建游戏状态
grid = Gridmap.from_text(map_text)
grid.expand()
grid.evaluate()

# 数据自动保存到 JSON 文件
dm = get_data_manager()
print(f"GameStates: {len(dm.gamestate_manager)}")
print(f"Targets: {len(dm.target_manager)}")
print(f"Plans: {len(dm.plan_manager)}")
```

### 3. 手动保存（如果 auto_save=False）

```python
from state_storage import save_all_data

# 手动保存所有数据
save_all_data()
```

### 4. 重新加载数据

```python
from state_storage import reload_all_data

# 从 JSON 文件重新加载数据
reload_all_data()
```

## API 详解

### JSONBackend 类

```python
class JSONBackend(StorageBackend):
    def __init__(self, filepath: str, auto_save: bool = True):
        """
        Args:
            filepath: JSON 文件路径
            auto_save: 是否在每次修改后自动保存
        """
```

**特性：**
- ✅ 线程安全（使用 RLock）
- ✅ 自动保存（可选）
- ✅ 原子性写入（临时文件 + rename）
- ✅ 懒加载（首次访问时读取）
- ✅ 修改追踪（避免不必要的保存）

**方法：**
- `save()` - 手动保存到文件
- `reload()` - 从文件重新加载（丢弃未保存的修改）

### 配置函数

#### configure_json_storage()

```python
def configure_json_storage(storage_dir: str = './data', 
                          auto_save: bool = True) -> tuple:
    """配置所有 manager 使用 JSON 存储
    
    Args:
        storage_dir: 存储目录路径
        auto_save: 是否在每次修改后自动保存
        
    Returns:
        tuple: (gamestate_backend, target_backend, plan_backend)
    """
```

创建三个 JSON 文件：
- `{storage_dir}/gamestates.json` - 所有游戏状态
- `{storage_dir}/targets.json` - 所有目标交互
- `{storage_dir}/plans.json` - 所有动作计划

#### save_all_data()

```python
def save_all_data() -> None:
    """保存所有后端的数据（如果使用的是 JSONBackend）"""
```

遍历所有 manager，如果使用 JSONBackend 则保存。

#### reload_all_data()

```python
def reload_all_data() -> None:
    """重新加载所有后端的数据（如果使用的是 JSONBackend）"""
```

从 JSON 文件重新加载数据，丢弃内存中未保存的修改。

## 使用场景

### 场景 1: 实验数据持久化

```python
# 配置 JSON 存储
configure_json_storage('./experiments/exp001')

# 运行实验
for trial in range(100):
    grid = Gridmap.from_text(map_text)
    grid.expand()
    actions, raw, norm = grid.evaluate()
    # ... 选择动作并执行 ...

# 数据自动保存到 ./experiments/exp001/
```

### 场景 2: 增量构建状态空间

```python
# Day 1: 探索部分状态空间
configure_json_storage('./state_space', auto_save=True)
explore_states(depth=5)
# 数据保存到 ./state_space/*.json

# Day 2: 继续探索
configure_json_storage('./state_space', auto_save=True)
# 自动加载之前的数据
explore_states(depth=10)  # 继续探索
```

### 场景 3: 批处理模式（延迟保存）

```python
# 批处理时禁用自动保存（提高性能）
configure_json_storage('./batch_data', auto_save=False)

# 处理大量数据
for map_name in all_maps:
    grid = process_map(map_name)
    # ... 不会立即保存 ...

# 批处理完成后一次性保存
save_all_data()
```

## 性能考虑

### Auto Save vs Manual Save

**Auto Save (auto_save=True)**
- ✅ 优点：数据安全，不会丢失
- ❌ 缺点：每次修改都写文件，较慢

**Manual Save (auto_save=False)**
- ✅ 优点：性能更好，批量写入
- ❌ 缺点：需要手动调用 `save_all_data()`

**建议：**
- 交互式探索：使用 `auto_save=True`
- 批量处理：使用 `auto_save=False` + 最后调用 `save_all_data()`
- 长时间运行：定期调用 `save_all_data()`

### 文件大小

JSON 文件大小取决于探索的状态空间：
- 简单地图（base）：~100 KB
- 复杂地图（maze）：~10 MB
- 完整探索：可能达到 100+ MB

**优化建议：**
- 使用 `ensure_ascii=False` 节省空间（已实现）
- 定期清理不需要的数据
- 考虑使用压缩（未来功能）

## 故障恢复

### 数据损坏

如果 JSON 文件损坏，加载时会打印警告并使用空字典：

```python
Warning: Failed to load ./data/gamestates.json: Expecting value: line 1 column 1 (char 0)
```

**解决方法：**
1. 检查文件内容
2. 删除损坏的文件
3. 重新运行探索

### 原子性保证

JSONBackend 使用临时文件 + rename 保证原子性：

```python
# 写入临时文件
with open('gamestates.tmp', 'w') as f:
    json.dump(data, f)

# 原子性替换
os.replace('gamestates.tmp', 'gamestates.json')
```

即使写入过程中崩溃，原文件也不会损坏。

## 与 InMemoryBackend 对比

| 特性 | InMemoryBackend | JSONBackend |
|------|-----------------|-------------|
| 持久化 | ❌ | ✅ |
| 性能 | 快 | 较慢（磁盘 I/O） |
| 内存占用 | 全部在内存 | 全部在内存 + 磁盘 |
| 线程安全 | ✅ | ✅ |
| 故障恢复 | ❌ | ✅ |
| 适用场景 | 临时测试 | 生产、实验 |

## 示例：完整工作流

```python
# ========== 配置阶段 ==========
from state_storage import configure_json_storage, save_all_data
from recorder import Gridmap, get_data_manager

# 配置 JSON 存储
configure_json_storage('./experiment_data', auto_save=True)

# ========== 探索阶段 ==========
grid = Gridmap.from_text(map_text)

# 1. Summary
summary = grid.summarizer.summary(grid)
print(f"Rules: {len(summary['info']['rules'])}")

# 2. Expand
grid.expand()
dm = get_data_manager()
print(f"Found {len(dm.target_manager)} targets")

# 3. Evaluate
actions, raw, norm = grid.evaluator.evaluate_plan_space(grid)
print(f"Evaluated {len(actions)} plans")

# ========== 数据已自动保存 ==========
print(f"\nData saved to:")
print(f"  GameStates: {len(dm.gamestate_manager)} states")
print(f"  Targets: {len(dm.target_manager)} interactions")
print(f"  Plans: {len(dm.plan_manager)} plans")

# ========== 下次运行时自动加载 ==========
# 只需再次配置相同路径即可
configure_json_storage('./experiment_data')
# 数据已自动加载！
```

## 注意事项

1. **首次配置**：必须在创建任何 Gridmap 之前调用 `configure_json_storage()`
2. **目录权限**：确保有写入权限
3. **文件冲突**：多个进程不要同时写入同一文件
4. **数据格式**：JSON 只支持基本类型，复杂对象需要序列化
5. **版本兼容**：JSON 格式变化可能导致旧数据不兼容

## 未来改进

- [ ] 压缩支持（gzip）
- [ ] 增量保存（只保存修改的部分）
- [ ] 数据库后端（SQLite）
- [ ] 远程存储（S3, Azure Blob）
- [ ] 版本控制（数据快照）
- [ ] 并发控制（多进程安全）
