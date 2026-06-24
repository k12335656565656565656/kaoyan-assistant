# Contributing

感谢你为这个项目贡献改进。

## Development Principles

- 优先保证可运行性和可维护性
- 新功能尽量通过 `services/`、`repositories/`、`schemas/` 分层实现
- 不要把敏感信息、本地数据库、日志和大体积测试资料提交到仓库
- 对外说明尽量更新到 `README.md` 或 `docs/`

## Recommended Workflow

1. 从最新主分支创建功能分支
2. 聚焦单一主题提交改动
3. 变更涉及运行方式时同步更新文档
4. 提交前至少完成一次基础自检

## Basic Checks

建议在提交前完成以下检查：

```bash
python -m compileall .
```

如果你改动了依赖或启动流程，也请补充一次本地启动验证。

## Commit Guidance

推荐使用清晰、聚焦的提交信息，例如：

- `feat: add adaptive OCR fallback for PDF ingestion`
- `fix: harden material routing for low quality extracts`
- `docs: add repository governance and security notes`
