from core.model_data import Grid3DData, GridAxisEntry, ProjectModel, load_project, save_project


def test_project_grid_is_persisted(tmp_path):
    project = ProjectModel(name="Grille test")
    project.grid = Grid3DData(
        enabled=True,
        x_items=[
            GridAxisEntry("A", 1.0),
            GridAxisEntry("B", 5.0),
            GridAxisEntry("C", 9.5),
        ],
        y_items=[
            GridAxisEntry("1", 2.0),
            GridAxisEntry("2", 8.0),
        ],
        z_items=[
            GridAxisEntry("N0", 0.5),
            GridAxisEntry("R+1", 3.7),
            GridAxisEntry("R+2", 7.4),
        ],
    )

    path = tmp_path / "grid_project.db"
    save_project(project, path)
    loaded = load_project(path)

    assert loaded.grid == project.grid


def test_grid_from_legacy_payload_keeps_regular_coordinates():
    grid = Grid3DData.from_dict(
        {
            "enabled": True,
            "origin_x": 1.0,
            "origin_y": 2.0,
            "origin_z": 0.5,
            "count_x": 2,
            "count_y": 1,
            "count_z": 2,
            "spacing_x": 4.0,
            "spacing_y": 6.0,
            "spacing_z": 3.2,
        }
    )

    assert grid.enabled is True
    assert grid.axis_values("X") == [1.0, 5.0, 9.0]
    assert grid.axis_values("Y") == [2.0, 8.0]
    assert grid.axis_values("Z") == [0.5, 3.7, 6.9]
