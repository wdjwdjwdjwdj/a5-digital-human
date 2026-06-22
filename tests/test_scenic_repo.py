"""景区数据仓储层单元测试：覆盖灵山胜境种子数据、景点 CRUD、路线关联查询。

参考 conftest.py 的 mock 模式，使用 tmp_path 创建临时 SQLite 数据库，
确保测试隔离，不污染生产数据。
"""

import sqlite3

import pytest

from backend.repository.scenic_repo import ScenicRepository


class TestScenicRepo:
    """ScenicRepository 完整测试套件（5 个测试用例）。"""

    @pytest.fixture(autouse=True)
    async def setup_repo(self, tmp_path: object) -> None:
        """每个测试前创建独立的临时数据库实例。"""
        db_path = tmp_path / "test_lingshan.db"
        self.repo = ScenicRepository(str(db_path))
        await self.repo.init_db()
        await self.repo.init_seed_data()
        self.db_path = str(db_path)
        yield
        await self.repo.close()

    # ────────────────────────────────────────────────────
    # 用例 1：种子数据插入验证
    # ────────────────────────────────────────────────────
    async def test_seed_data_inserted(self) -> None:
        """验证种子数据插入后各表记录数符合预期。"""
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.cursor()

            cursor.execute("SELECT COUNT(*) FROM scenic_spots")
            spot_count = cursor.fetchone()[0]
            assert spot_count == 16, f"scenic_spots 应为 16 条，实际 {spot_count}"

            cursor.execute("SELECT COUNT(*) FROM scenic_routes")
            route_count = cursor.fetchone()[0]
            assert route_count >= 3, f"scenic_routes 应为 >= 3 条，实际 {route_count}"

            cursor.execute("SELECT COUNT(*) FROM scenic_route_spots")
            rs_count = cursor.fetchone()[0]
            assert rs_count >= 8, f"scenic_route_spots 应为 >= 8 条，实际 {rs_count}"

            cursor.execute("SELECT COUNT(*) FROM scenic_activities")
            act_count = cursor.fetchone()[0]
            assert act_count >= 4, f"scenic_activities 应为 >= 4 条，实际 {act_count}"

            cursor.execute("SELECT COUNT(*) FROM scenic_area_info")
            area_count = cursor.fetchone()[0]
            assert area_count == 1, f"scenic_area_info 应为 1 条，实际 {area_count}"
        finally:
            conn.close()

    # ────────────────────────────────────────────────────
    # 用例 2：获取所有景点列表
    # ────────────────────────────────────────────────────
    async def test_get_all_spots(self) -> None:
        """查询所有景点列表，验证返回 16 个且包含关键景点名称。"""
        spots = await self.repo.get_spots()
        assert isinstance(spots, list)
        assert len(spots) == 16, f"景点数应为 16，实际 {len(spots)}"

        spot_names = [s["name"] for s in spots]
        for expected_name in ("灵山大佛", "灵山梵宫", "九龙灌浴", "五印坛城", "祥符禅寺"):
            assert expected_name in spot_names, f"缺少景点: {expected_name}"

    # ────────────────────────────────────────────────────
    # 用例 3：按 spot_id 查询景点详情
    # ────────────────────────────────────────────────────
    async def test_get_spot_by_spot_id(self) -> None:
        """按 spot_id 查询景点详情，验证字段完整。"""
        # 查询灵山大佛（LS-011）
        spot = await self.repo.get_spot_by_spot_id("LS-011")
        assert spot is not None, "LS-011（灵山大佛）不应返回 None"
        assert spot["name"] == "灵山大佛"
        assert spot["description"] is not None and len(spot["description"]) > 0
        assert spot.get("category") is not None
        assert spot.get("highlights") is not None

        # 查询不存在的 spot_id
        not_found = await self.repo.get_spot_by_spot_id("LS-999")
        assert not_found is None, "不存在的 spot_id 应返回 None"

    # ────────────────────────────────────────────────────
    # 用例 4：景点 CRUD 完整操作
    # ────────────────────────────────────────────────────
    async def test_create_update_delete_spot(self) -> None:
        """测试景点创建、更新、删除全生命周期。"""
        # CREATE
        new_spot = await self.repo.create_spot({
            "name": "测试景点",
            "category": "测试分类",
            "position": "测试位置",
            "highlights": "测试亮点",
            "description": "这是一个测试景点",
            "rating": 4.0,
            "ticket_price": "免费",
        })
        assert new_spot is not None, "创建景点不应返回 None"
        assert new_spot["name"] == "测试景点"
        spot_id = new_spot["spot_id"]
        assert spot_id.startswith("LS-"), f"spot_id 应以 LS- 开头，实际 {spot_id}"

        # READ（验证创建后可查询）
        fetched = await self.repo.get_spot_by_spot_id(spot_id)
        assert fetched is not None
        assert fetched["name"] == "测试景点"
        assert fetched["category"] == "测试分类"

        # UPDATE
        updated = await self.repo.update_spot(spot_id, {
            "name": "测试景点(已更新)",
            "description": "更新后的描述",
        })
        assert updated is not None
        assert updated["name"] == "测试景点(已更新)"
        assert updated["description"] == "更新后的描述"

        # DELETE
        deleted = await self.repo.delete_spot(spot_id)
        assert deleted is True, "删除应返回 True"

        # 确认已删除
        after_delete = await self.repo.get_spot_by_spot_id(spot_id)
        assert after_delete is None, "删除后查询应返回 None"

        # 删除不存在的记录不应抛异常
        deleted_nonexist = await self.repo.delete_spot("LS-999")
        assert deleted_nonexist is False, "删除不存在的记录应返回 False"

    # ────────────────────────────────────────────────────
    # 用例 5：路线关联景点查询
    # ────────────────────────────────────────────────────
    async def test_get_routes_with_spots(self) -> None:
        """测试路线与景点的多对多关联查询。"""
        routes = await self.repo.get_routes()
        assert isinstance(routes, list)
        assert len(routes) >= 3, f"路线数应 >= 3，实际 {len(routes)}"

        # 验证每条路线都关联了景点
        for route in routes:
            assert "spots" in route, f"路线 {route['name']} 缺少 spots 字段"
            assert len(route["spots"]) > 0, f"路线 {route['name']} 未关联任何景点"

        # 验证"经典祈福线路"关联了至少 5 个景点
        classic = next((r for r in routes if "经典祈福" in r["name"]), None)
        assert classic is not None, "未找到经典祈福线路"
        assert len(classic["spots"]) >= 5, (
            f"经典祈福线路应关联 >= 5 个景点，实际 {len(classic['spots'])}"
        )

        # 验证"灵山大佛"出现在至少 1 条路线中
        spot_in_route = False
        for route in routes:
            for spot in route["spots"]:
                if spot.get("spot_id") == "LS-011" or spot.get("name") == "灵山大佛":
                    spot_in_route = True
                    break
        assert spot_in_route, "灵山大佛应出现在至少 1 条路线中"

        # 验证按 ID 查询单条路线
        route_detail = await self.repo.get_route_by_id(1)
        assert route_detail is not None
        assert "spots" in route_detail
