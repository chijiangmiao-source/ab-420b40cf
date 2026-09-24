# Emergency-Stop Relay Network Auditor

审计大型加速器紧急停束继电网络的单点故障：对 `POST /api/audit` 提交的有向图，
在根控制器的可达子图上计算每个节点的**立即支配者**（immediate dominator）**，
并汇总每个非根非终端中间继电器所**支配的保护终端（执行器）数量**——支配即
"该继电器失效则这些终端必然失联"。存在旁路的节点（如菱形结构）不会被误报。

## 核心算法

- **Lengauer–Tarjan** 立即支配者算法（四步经典版，带路径压缩），
  时间复杂度约 `O(E · α(V))`，单次遍历完成，**不逐节点删边重跑可达性**。
- DFS、路径压缩、子树计数全部为**迭代实现**，20 万深链也不会触发递归限制。
- 不依赖任何图算法库（仅 FastAPI / Pydantic / Uvicorn）。
- 支配终端计数：支配树中祖先的 dfs 序号恒小于后代，按 dfs 逆序一趟累加即可。

## API

### `POST /api/audit`

```json
{
  "root": "R",
  "nodes": ["R", "A", "B", "T"],
  "terminals": ["T"],
  "edges": [["R", "A"], ["R", "B"], ["A", "T"], ["B", "T"]]
}
```

约束：2–200000 个唯一 ASCII 节点；1–20000 个无出边保护终端（须为节点子集）；
至多 500000 条有向边；允许平行边，禁止自环；root 必须已声明。

200 响应（三个列表均按节点标识排序）：

```json
{
  "unreachable_terminals": [],
  "immediate_dominators": [
    {"node": "A", "idom": "R"},
    {"node": "B", "idom": "R"},
    {"node": "T", "idom": "R"}
  ],
  "critical_relays": []
}
```

输入非法（悬空引用 / 重复标识 / 终端带出边 / 自环 / 数量越界）时返回
**422 + 可定位错误列表**，绝不返回部分审计结果：

```json
{"detail": [{"loc": ["body", "edges", 0, 1], "msg": "dangling reference: unknown node 'GHOST'", "type": "dangling_reference"}]}
```

### `GET /health`

服务就绪时返回 `200 {"status": "ok"}`，否则 `503`；Compose 健康检查依赖此路径。

## 运行

```bash
# 构建并启动服务（宿主机端口由 HOST_PORT 控制，默认 8000）
HOST_PORT=9000 docker compose up --build app

# 一键验证：单元测试 + 应用构建检查 + HTTP 冒烟（菱形旁路 / 串联关键点 /
# 平行边 / 不可达终端 / 错误定位），单次执行，退出码即结论
docker compose up --build --exit-code-from verify
```

## 本地开发

```bash
pip install -r requirements-dev.txt
python -m pytest tests -q          # 单元测试（含暴力对拍与 20 万深链）
python -m uvicorn app.main:app --port 8000
python scripts/verify.py           # 完整验证（需服务已启动）
```

## 结构

```
app/
  main.py        FastAPI 应用、/api/audit 与 /health、错误处理
  schemas.py     请求/响应模型与数量约束
  validation.py  语义校验（悬空引用、重复标识、终端出边、自环）
  dominators.py  迭代式 Lengauer–Tarjan 支配者核心
  audit.py       可达子图汇总：idom、支配终端计数、排序输出
tests/           单元测试（随机图暴力对拍、深链、API 行为）
scripts/         verify.py（总控）/ build_check.py / smoke.py
Dockerfile       runtime 与 verify 双阶段镜像（Python 3.13）
docker-compose.yml  app（健康检查、可配置端口）+ verify（一次性）
```
