import csv
import pytest

from pathlib import Path

from dbt.tests.util import (
    run_dbt,
    read_file,
    check_relations_equal,
    check_table_does_exist,
    check_table_does_not_exist,
)
from tests.functional.simple_seed.fixtures import (
    models__downstream_from_seed_actual,
    models__from_basic_seed,
    seeds__disabled_in_config,
    seeds__enabled_in_config,
    seeds__tricky,
    seeds__wont_parse,
)

# from `test/integration/test_simple_seed`, test_simple_seed


class SeedConfigBase(object):
    @pytest.fixture(scope="class")
    def project_config_update(self):
        return {
            "seeds": {
                "quote_columns": False,
            },
        }


class SeedTestBase(SeedConfigBase):
    @pytest.fixture(scope="class", autouse=True)
    def setUp(self, project):
        """Create table for ensuring seeds and models used in tests build correctly"""
        project.run_sql_file(project.test_data_dir / Path("seed_expected.sql"))

    @pytest.fixture(scope="class")
    def seeds(self, test_data_dir):
        seed_actual_csv = read_file(test_data_dir, "seed_actual.csv")
        return {"seed_actual.csv": seed_actual_csv}

    @pytest.fixture(scope="class")
    def models(self):
        return {
            "models__downstream_from_seed_actual.sql": models__downstream_from_seed_actual,
        }

    def _build_relations_for_test(self, project):
        """The testing environment needs seeds and models to interact with"""
        seed_result = run_dbt(["seed"])
        assert len(seed_result) == 1
        check_relations_equal(project.adapter, ["seed_expected", "seed_actual"])

        run_result = run_dbt()
        assert len(run_result) == 1
        check_relations_equal(
            project.adapter, ["models__downstream_from_seed_actual", "seed_expected"]
        )

    def _check_relation_end_state(self, run_result, project, exists: bool):
        assert len(run_result) == 1
        check_relations_equal(project.adapter, ["seed_actual", "seed_expected"])
        if exists:
            check_table_does_exist(project.adapter, "models__downstream_from_seed_actual")
        else:
            check_table_does_not_exist(project.adapter, "models__downstream_from_seed_actual")


class TestBasicSeedTests(SeedTestBase):
    def test_simple_seed(self, project):
        """Build models and observe that run truncates a seed and re-inserts rows"""
        self._build_relations_for_test(project)
        self._check_relation_end_state(run_result=run_dbt(["seed"]), project=project, exists=True)

    def test_simple_seed_full_refresh_flag(self, project):
        """Drop the seed_actual table and re-create. Verifies correct behavior by the absence of the
        model which depends on seed_actual."""
        self._build_relations_for_test(project)
        self._check_relation_end_state(
            run_result=run_dbt(["seed", "--full-refresh"]), project=project, exists=False
        )


class TestSeedConfigFullRefreshOn(SeedTestBase):
    @pytest.fixture(scope="class")
    def project_config_update(self):
        return {
            "seeds": {"quote_columns": False, "full_refresh": True},
        }

    def test_simple_seed_full_refresh_config(self, project):
        """config option should drop current model and cascade drop to downstream models"""
        self._build_relations_for_test(project)
        self._check_relation_end_state(run_result=run_dbt(["seed"]), project=project, exists=False)


class TestSeedConfigFullRefreshOff(SeedTestBase):
    @pytest.fixture(scope="class")
    def project_config_update(self):
        return {
            "seeds": {"quote_columns": False, "full_refresh": False},
        }

    def test_simple_seed_full_refresh_config(self, project):
        """Config options should override full-refresh flag because config is higher priority"""
        self._build_relations_for_test(project)
        self._check_relation_end_state(run_result=run_dbt(["seed"]), project=project, exists=True)
        self._check_relation_end_state(
            run_result=run_dbt(["seed", "--full-refresh"]), project=project, exists=True
        )


class TestSeedCustomSchema(SeedTestBase):
    @pytest.fixture(scope="class", autouse=True)
    def setUp(self, project):
        """Create table for ensuring seeds and models used in tests build correctly"""
        project.run_sql_file(project.test_data_dir / Path("seed_expected.sql"))

    @pytest.fixture(scope="class")
    def project_config_update(self):
        return {
            "seeds": {
                "schema": "custom_schema",
                "quote_columns": False,
            },
        }

    def test_simple_seed_with_schema(self, project):
        results = run_dbt(["seed"])
        assert len(results) == 1
        custom_schema = f"{project.test_schema}_custom_schema"
        check_relations_equal(project.adapter, [f"{custom_schema}.seed_actual", "seed_expected"])

        # this should truncate the seed_actual table, then re-insert
        results = run_dbt(["seed"])
        assert len(results) == 1
        custom_schema = f"{project.test_schema}_custom_schema"
        check_relations_equal(project.adapter, [f"{custom_schema}.seed_actual", "seed_expected"])

    def test_simple_seed_with_drop_and_schema(self, project):
        results = run_dbt(["seed"])
        assert len(results) == 1
        custom_schema = f"{project.test_schema}_custom_schema"
        check_relations_equal(project.adapter, [f"{custom_schema}.seed_actual", "seed_expected"])

        # this should drop the seed table, then re-create
        results = run_dbt(["seed", "--full-refresh"])
        custom_schema = f"{project.test_schema}_custom_schema"
        check_relations_equal(project.adapter, [f"{custom_schema}.seed_actual", "seed_expected"])


class TestSimpleSeedEnabledViaConfig(object):
    @pytest.fixture(scope="session")
    def seeds(self):
        return {
            "seed_enabled.csv": seeds__enabled_in_config,
            "seed_disabled.csv": seeds__disabled_in_config,
            "seed_tricky.csv": seeds__tricky,
        }

    @pytest.fixture(scope="class")
    def project_config_update(self):
        return {
            "seeds": {
                "test": {"seed_enabled": {"enabled": True}, "seed_disabled": {"enabled": False}},
                "quote_columns": False,
            },
        }

    @pytest.fixture(scope="function")
    def clear_test_schema(self, project):
        yield
        project.run_sql(f"drop schema if exists {project.test_schema} cascade")

    def test_simple_seed_with_disabled(self, clear_test_schema, project):
        results = run_dbt(["seed"])
        len(results) == 2
        check_table_does_exist(project.adapter, "seed_enabled")
        check_table_does_not_exist(project.adapter, "seed_disabled")
        check_table_does_exist(project.adapter, "seed_tricky")

    def test_simple_seed_selection(self, clear_test_schema, project):
        results = run_dbt(["seed", "--select", "seed_enabled"])
        len(results) == 1
        check_table_does_exist(project.adapter, "seed_enabled")
        check_table_does_not_exist(project.adapter, "seed_disabled")
        check_table_does_not_exist(project.adapter, "seed_tricky")

    def test_simple_seed_exclude(self, clear_test_schema, project):
        results = run_dbt(["seed", "--exclude", "seed_enabled"])
        len(results) == 1
        check_table_does_not_exist(project.adapter, "seed_enabled")
        check_table_does_not_exist(project.adapter, "seed_disabled")
        check_table_does_exist(project.adapter, "seed_tricky")


class TestSeedParsing(SeedConfigBase):
    @pytest.fixture(scope="class", autouse=True)
    def setUp(self, project):
        """Create table for ensuring seeds and models used in tests build correctly"""
        project.run_sql_file(project.test_data_dir / Path("seed_expected.sql"))

    @pytest.fixture(scope="class")
    def seeds(self):
        return {"seed.csv": seeds__wont_parse}

    @pytest.fixture(scope="class")
    def models(self):
        return {"model.sql": models__from_basic_seed}

    def test_dbt_run_skips_seeds(self, project):
        # run does not try to parse the seed files
        len(run_dbt()) == 1

        # make sure 'dbt seed' fails, otherwise our test is invalid!
        run_dbt(["seed"], expect_pass=False)


class TestSimpleSeedWithBOM(SeedConfigBase):
    @pytest.fixture(scope="class", autouse=True)
    def setUp(self, project):
        """Create table for ensuring seeds and models used in tests build correctly"""
        project.run_sql_file(project.test_data_dir / Path("seed_expected.sql"))

    @pytest.fixture(scope="class")
    def seeds(self, test_data_dir):
        seed_bom = read_file(test_data_dir, "seed_bom.csv")
        return {"seed_bom.csv": seed_bom}

    def test_simple_seed(self, project):
        # first make sure nobody "fixed" the file by accident
        seed_path = project.test_data_dir / Path("seed_bom.csv")
        with open(seed_path, encoding="utf-8") as fp:
            assert fp.read(1) == "\ufeff"

        results = run_dbt(["seed"])
        len(results) == 1
        check_relations_equal(project.adapter, ["seed_expected", "seed_bom"])


class TestSimpleSeedWithUnicode(SeedConfigBase):
    @pytest.fixture(scope="class")
    def seeds(self, test_data_dir):
        seed_unicode = read_file(test_data_dir, "seed_unicode.csv")
        return {"seed_unicode.csv": seed_unicode}

    def test_simple_seed(self, project):
        results = run_dbt(["seed"])
        len(results) == 1


class TestSimpleSeedWithDots(SeedConfigBase):
    @pytest.fixture(scope="class")
    def seeds(self, test_data_dir):
        dotted_seed = read_file(test_data_dir, "seed.with.dots.csv")
        return {"seed.with.dots.csv": dotted_seed}

    def test_simple_seed(self, project):
        results = run_dbt(["seed"])
        len(results) == 1


class TestSimpleBigSeedBatched(SeedConfigBase):
    def test_postgres_big_batched_seed(self, project):
        big_seed = project.test_data_dir / Path("big-seed.csv")
        with open(big_seed, "w") as f:
            writer = csv.writer(f)
            writer.writerow(["id"])
            for i in range(0, 20000):
                writer.writerow([i])

        results = run_dbt(["seed"])
        len(results) == 1
