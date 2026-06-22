#!/usr/bin/env bash
# =============================================================================
# scripts/verify_lingshan.sh — 灵山胜境迁移 MUST-PASS 一键验证
# 用法: bash scripts/verify_lingshan.sh
# =============================================================================
# 兼容 Git Bash (Windows) 和 Linux/macOS
# 依赖: Python 虚拟环境已激活, ruff, pytest, curl
# 端口 8000 需未被占用（用于 C2 API 验证）
# =============================================================================

set -e

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PASS_COUNT=0
FAIL_COUNT=0
RESULTS=()

# ── 颜色 ──
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

pass() { echo -e "${GREEN}[PASS]${NC} $1"; ((PASS_COUNT++)); RESULTS+=("PASS|$1"); }
fail() { echo -e "${RED}[FAIL]${NC} $1"; ((FAIL_COUNT++)); RESULTS+=("FAIL|$1"); }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; RESULTS+=("WARN|$1"); }

echo ""
echo "=========================================="
echo "  灵山胜境迁移 — MUST-PASS 验证"
echo "=========================================="
echo ""

# ──────────────────────────────────────────────
# C1: 西湖码残留检查（白名单除外）
# ──────────────────────────────────────────────
echo "------------------------------------------"
echo " C1 | 西湖名称残留检查"
echo "------------------------------------------"
RESIDUAL=$(grep -rn "西湖" --include="*.py" --include="*.md" --include="*.html" \
  "$PROJECT_DIR/backend/" "$PROJECT_DIR/tests/" "$PROJECT_DIR/knowledge/" \
  "$PROJECT_DIR/scripts/" 2>/dev/null | grep -v "西湖龙井" | grep -v "西湖醋鱼" \
  | grep -v "西湖博物馆" || true)
if [ -z "$RESIDUAL" ]; then
  pass "C1: 无西湖残留"
else
  fail "C1: 发现西湖残留:"
  echo "$RESIDUAL"
fi
echo ""

# ──────────────────────────────────────────────
# C2: API 16 景点验证
# ──────────────────────────────────────────────
echo "------------------------------------------"
echo " C2 | API 返回 16 个景点"
echo "------------------------------------------"
cd "$PROJECT_DIR"
python main.py &
SERVER_PID=$!
sleep 3
SPOT_COUNT=$(curl -s http://localhost:8000/api/v1/scenic/spots 2>/dev/null \
  | python -c "import sys,json; d=json.load(sys.stdin); spots=d.get('data',[]); print(len(spots))" 2>/dev/null || echo "0")
kill $SERVER_PID 2>/dev/null || true
wait $SERVER_PID 2>/dev/null || true
if [ "$SPOT_COUNT" = "16" ]; then
  pass "C2: API 返回 16 个景点"
else
  fail "C2: 期望 16 个景点，实际获取 $SPOT_COUNT"
fi
echo ""

# ──────────────────────────────────────────────
# C3: pytest 全部通过
# ──────────────────────────────────────────────
echo "------------------------------------------"
echo " C3 | pytest 测试"
echo "------------------------------------------"
cd "$PROJECT_DIR"
if python -m pytest tests/ -v --tb=short 2>&1; then
  pass "C3: pytest 全部通过"
else
  fail "C3: pytest 存在失败用例"
fi
echo ""

# ──────────────────────────────────────────────
# C4: ruff 零 Error
# ──────────────────────────────────────────────
echo "------------------------------------------"
echo " C4 | ruff 代码检查"
echo "------------------------------------------"
cd "$PROJECT_DIR"
if ruff check . 2>&1; then
  pass "C4: ruff 零 Error"
else
  fail "C4: ruff 报告 Error"
fi
echo ""

# ──────────────────────────────────────────────
# C5: 准确率测试（参考项，非 MUST-PASS）
# ──────────────────────────────────────────────
echo "------------------------------------------"
echo " C5 | 准确率测试 ≥ 90%"
echo "------------------------------------------"
cd "$PROJECT_DIR"
if python scripts/test_accuracy.py 2>&1; then
  pass "C5: 准确率测试通过"
else
  warn "C5: 准确率测试未通过（非阻塞，请检查知识库数据）"
fi
echo ""

# ──────────────────────────────────────────────
# 汇总
# ──────────────────────────────────────────────
echo "=========================================="
echo "  验证汇总"
echo "=========================================="
for R in "${RESULTS[@]}"; do
  IFS='|' read -r STATUS ITEM <<< "$R"
  case "$STATUS" in
    PASS) echo -e "  ${GREEN}[PASS]${NC} $ITEM" ;;
    FAIL) echo -e "  ${RED}[FAIL]${NC} $ITEM" ;;
    WARN) echo -e "  ${YELLOW}[WARN]${NC} $ITEM" ;;
  esac
done
echo ""
echo -e "  总计: ${GREEN}$PASS_COUNT PASS${NC}, ${RED}$FAIL_COUNT FAIL${NC}"
echo "=========================================="

# 退出码：FAIL > 0 时返回 1
[ "$FAIL_COUNT" -eq 0 ]
