from crime import grid


def test_base_cells_cover_daejeon_bbox_with_2km_cells():
    cells = grid.base_cells()

    assert cells  # 대전 bbox를 덮는 셀이 적어도 하나는 있어야 한다
    for minx, miny, size_m in cells:
        assert size_m == grid.CELL_SIZE_M
        # 2000m 배수로 스냅돼 있어야 자식 셀 분할과 겹치지 않는다
        assert minx % grid.CELL_SIZE_M == 0
        assert miny % grid.CELL_SIZE_M == 0


def test_base_cells_are_unique():
    cells = grid.base_cells()
    ids = [grid.cell_id(minx, miny, size_m) for minx, miny, size_m in cells]

    assert len(ids) == len(set(ids))


def test_split_cell_produces_four_quadrants_half_size():
    children = grid.split_cell(0, 0, 2000)

    assert len(children) == 4
    assert all(size_m == 1000 for _, _, size_m in children)
    xs = {minx for minx, _, _ in children}
    ys = {miny for _, miny, _ in children}
    assert xs == {0, 1000}
    assert ys == {0, 1000}


def test_split_cell_children_tile_the_parent_without_gaps_or_overlap():
    parent_bbox = grid.cell_bbox(0, 0, 2000)
    children = grid.split_cell(0, 0, 2000)
    child_bboxes = [grid.cell_bbox(minx, miny, size_m) for minx, miny, size_m in children]

    total_child_area = sum(
        (maxx - minx) * (maxy - miny) for minx, miny, maxx, maxy in child_bboxes
    )
    parent_area = (parent_bbox[2] - parent_bbox[0]) * (parent_bbox[3] - parent_bbox[1])
    assert total_child_area == parent_area


def test_cell_id_differs_between_parent_and_child_at_same_origin():
    """부모(2000m)와 자식(1000m)이 같은 좌표에서 시작해도 크기가 cell_id에 들어가 충돌하지 않는다."""
    parent_id = grid.cell_id(0, 0, 2000)
    child_id = grid.cell_id(0, 0, 1000)

    assert parent_id != child_id


def test_cell_bbox_matches_minx_miny_size():
    assert grid.cell_bbox(100, 200, 2000) == (100, 200, 2100, 2200)
