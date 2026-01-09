# Decision Register Entry

## Decision ID
`DR-2025-01-09-001`

## Title
Frontend Port Allocation: 5173 instead of 3000

## Status
✅ **Approved & Implemented**

## Context
用户在项目初始化时明确指出：**localhost端口3000已经被占用**。需要为前端开发服务器选择替代端口。

## Decision
**前端使用端口 5173（Vite默认端口）**

## Rationale
1. **避免冲突**: 3000端口已被占用
2. **工具链默认**: 5173是Vite的默认端口，无需额外配置
3. **开发者体验**: 保持工具链约定，降低认知负担
4. **文档一致性**: 所有文档和配置统一使用5173

## Alternatives Considered
| 选项 | 优点 | 缺点 | 决策 |
|------|------|------|------|
| 3000 | React生态常用 | 已被占用 | ❌ 拒绝 |
| 5173 | Vite默认，无需配置 | 非React传统端口 | ✅ 采纳 |
| 3001 | 接近3000 | 需要额外配置 | ❌ 拒绝 |
| 8080 | 常见备用端口 | 可能与其他服务冲突 | ❌ 拒绝 |

## Impact
### 影响范围
- `frontend/vite.config.ts` - server.port配置
- `frontend/.env` - VITE_API_URL配置
- `docker-compose.yml` - frontend服务端口映射
- `README.md` - 文档说明
- `PROJECT_STRUCTURE.md` - 端口说明

### 影响的AI角色
- Frontend AI: 需要知道正确的开发端口
- Ops AI: 需要配置正确的端口映射
- Reviewer AI: 需要验证端口配置一致性

## Authority
- **来源**: 用户需求（明确指出3000端口冲突）
- **规范层级**: L2 (实现细节)
- **裁决者**: Architect AI

## Implementation
```typescript
// frontend/vite.config.ts
export default defineConfig({
  server: {
    port: 5173, // ✅ 使用Vite默认端口
  },
})
```

```yaml
# docker-compose.yml
services:
  frontend:
    ports:
      - "5173:5173"  # ✅ 映射到5173
```

## Validation
- [x] 前端可在 http://localhost:5173 访问
- [x] Docker容器端口映射正确
- [x] 所有文档已更新

## Related Decisions
- 无

## Notes
此决策为**实现细节**，不影响架构核心设计，无需进入高优先级决策登记。

---

**Created by:** Architect AI – Kiro  
**Date:** 2025-01-09  
**Last Updated:** 2025-01-09