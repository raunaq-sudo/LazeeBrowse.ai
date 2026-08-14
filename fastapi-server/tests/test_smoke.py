import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

import db
from config import get_model_list, get_models


def test_model_list_is_nonempty_and_well_formed():
    models = get_model_list()
    assert models, "model registry should not be empty"
    tags = {m["tag"] for m in models}
    for m in models:
        assert m["tag"], "every model needs a tag"
        assert m["provider"], "every model needs a provider"
        assert m["label"], "every model needs a label"
    assert len(tags) == len(models), "model tags must be unique"


def test_get_models_rejects_unknown_tag():
    with pytest.raises(ValueError, match="Unknown model tag"):
        asyncio.run(get_models(api_key="sk-test", model_tag="does-not-exist"))


def test_db_round_trip(tmp_path, monkeypatch):
    db_path = tmp_path / "settings.db"
    monkeypatch.setattr(db, "DB_PATH", str(db_path))
    assert db.get_setting("project_dir") is None
    db.set_setting("project_dir", "/tmp/example")
    assert db.get_setting("project_dir") == "/tmp/example"
