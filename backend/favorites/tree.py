"""즐겨찾기 폴더 트리 헬퍼 — 깊이·순환 검사, 트리 조립(spec 6-5: 폴더 수가 적어 재귀 쿼리
불필요, 사용자 폴더 전체를 한 번에 읽어 메모리에서 처리)."""

MAX_DEPTH = 5


def depth_of(folder_id, folders_by_id) -> int:
    """folder_id의 깊이(루트=1). folder_id가 None이면 0(최상위 바로 아래 깊이 계산용)."""
    depth = 0
    current = folder_id
    while current is not None:
        depth += 1
        current = folders_by_id[current].parent_id
    return depth


def subtree_height(folder_id, folders_by_id) -> int:
    """folder_id 서브트리의 최대 깊이(자기 자신=0, 자식 쪽으로 갈수록 +1)."""
    children = [f.id for f in folders_by_id.values() if f.parent_id == folder_id]
    if not children:
        return 0
    return 1 + max(subtree_height(child_id, folders_by_id) for child_id in children)


def is_descendant_or_self(candidate_id, ancestor_id, folders_by_id) -> bool:
    """candidate_id가 ancestor_id의 하위(또는 자기 자신)인지."""
    current = candidate_id
    while current is not None:
        if current == ancestor_id:
            return True
        current = folders_by_id[current].parent_id
    return False


def descendant_ids(folder_id, folders_by_id) -> list:
    """folder_id의 모든 하위 폴더 id(자기 자신 제외)."""
    result = []
    children = [f.id for f in folders_by_id.values() if f.parent_id == folder_id]
    for child_id in children:
        result.append(child_id)
        result.extend(descendant_ids(child_id, folders_by_id))
    return result


def nearest_color(folder_id, folders_by_id, default_color):
    """folder_id부터 조상 쪽으로 올라가며 처음 만나는 color(spec 10-4 색상 우선순위)."""
    current = folder_id
    while current is not None:
        folder = folders_by_id.get(current)
        if folder is None:
            break
        if folder.color:
            return folder.color
        current = folder.parent_id
    return default_color


def is_hidden(folder_id, folders_by_id) -> bool:
    """folder_id 자신 또는 조상 중 하나라도 is_hidden이면 True(spec 10-4: 숨김 폴더 전파)."""
    current = folder_id
    while current is not None:
        folder = folders_by_id.get(current)
        if folder is None:
            break
        if folder.is_hidden:
            return True
        current = folder.parent_id
    return False


def build_tree(folders, building_counts: dict) -> list:
    """folders: 사용자의 FavoriteFolder 전체. building_counts: {folder_id_or_None: count}.
    반환: spec 6-5 예시 모양(최상위들 + 맨 끝에 미분류 id=None)."""
    children_map: dict = {}
    for folder in folders:
        children_map.setdefault(folder.parent_id, []).append(folder)
    for key in children_map:
        children_map[key].sort(key=lambda f: f.sort_order)

    def serialize(folder):
        return {
            "id": folder.id,
            "name": folder.name,
            "color": folder.color,
            "is_hidden": folder.is_hidden,
            "building_count": building_counts.get(folder.id, 0),
            "children": [serialize(child) for child in children_map.get(folder.id, [])],
        }

    tree = [serialize(folder) for folder in children_map.get(None, [])]
    tree.append(
        {
            "id": None,
            "name": "미분류",
            "building_count": building_counts.get(None, 0),
            "children": [],
        }
    )
    return tree
