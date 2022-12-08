import pytest
from dbt.tests.util import (
    run_dbt,
    get_manifest,
    run_dbt_and_capture
)


my_model_sql = """
{{
  config(
    materialized = "table"
  )
}}

select
  1 as id,
  'blue' as color,
  cast('2019-01-01' as date) as date_day
"""

my_model_constraints_disabled_sql = """
{{
  config(
    materialized = "table",
    constraints_enabled = false
  )
}}

select
  1 as id,
  'blue' as color,
  cast('2019-01-01' as date) as date_day
"""

model_schema_yml = """
version: 2
models:
  - name: my_model
    config:
      constraints_enabled: true
    columns:
      - name: id
        data_type: integer
        description: hello
        constraints: ['not null','primary key']
        check: (id > 0)
        tests:
          - unique
      - name: color
        data_type: text
      - name: date_day
        data_type: date
"""

my_model_error_sql = """
{{
  config(
    materialized = "view"
  )
}}

select
  1 as id,
  'blue' as color,
  cast('2019-01-01' as date) as date_day
"""

my_model_python_error = """
import holidays, s3fs


def model(dbt, _):
    dbt.config(
        materialized="table",
        packages=["holidays", "s3fs"],  # how to import python libraries in dbt's context
        constraints_enabled=True,
    )
    df = dbt.ref("my_model")
    df_describe = df.describe()  # basic statistics profiling
    return df_describe
"""

model_schema_errors_yml = """
version: 2
models:
  - name: my_model
    config:
      constraints_enabled: true
    columns:
      - name: id
        data_type: integer
        description: hello
        constraints: ['not null','primary key']
        check: (id > 0)
        tests:
          - unique
      - name: color
        data_type: text
      - name: date_day
"""


class BaseConstraintsEnabledModelvsProject:
    @pytest.fixture(scope="class")
    def project_config_update(self):
        return {
            "models": {
                "test": {
                    "+constraints_enabled": True,
                    "subdirectory": {
                        "+constraints_enabled": False,
                    },
                }
            }
        }


class TestModelLevelConstraintsEnabledConfigs(BaseConstraintsEnabledModelvsProject):
    @pytest.fixture(scope="class")
    def models(self):
        return {
            "my_model.sql": my_model_sql,
            "constraints_schema.yml": model_schema_yml,
        }

    def test__model_constraints_enabled_true(self, project):

        run_dbt(["run"])
        manifest = get_manifest(project.project_root)
        model_id = "model.test.my_model"
        my_model_columns = manifest.nodes[model_id].columns
        my_model_config = manifest.nodes[model_id].config
        constraints_enabled_actual_config = my_model_config.constraints_enabled

        assert constraints_enabled_actual_config is True

        expected_columns = "{'id': ColumnInfo(name='id', description='hello', meta={}, data_type='integer', constraints=['not null', 'primary key'], check='(id > 0)', quote=None, tags=[], _extra={}), 'color': ColumnInfo(name='color', description='', meta={}, data_type='text', constraints=None, check=None, quote=None, tags=[], _extra={}), 'date_day': ColumnInfo(name='date_day', description='', meta={}, data_type='date', constraints=None, check=None, quote=None, tags=[], _extra={})}"

        assert expected_columns == str(my_model_columns)


class TestModelLevelConstraintsDisabledConfigs(BaseConstraintsEnabledModelvsProject):
    @pytest.fixture(scope="class")
    def models(self):
        return {
            "my_model.sql": my_model_constraints_disabled_sql,
            "constraints_schema.yml": model_schema_yml,
        }

    def test__model_constraints_enabled_false(self, project):

        run_dbt(["run"])
        manifest = get_manifest(project.project_root)
        model_id = "model.test.my_model"
        my_model_config = manifest.nodes[model_id].config
        constraints_enabled_actual_config = my_model_config.constraints_enabled

        assert constraints_enabled_actual_config is False


class TestSchemaConstraintsEnabledConfigs(BaseConstraintsEnabledModelvsProject):
    @pytest.fixture(scope="class")
    def models(self):
        return {
            "my_model.sql": my_model_sql,
        }

    def test__schema_error(self, project):
        schema_error_expected = "Schema Error: `yml` configuration does NOT exist"
        results, log_output = run_dbt_and_capture(['run'], expect_pass=False)
        assert schema_error_expected in log_output


class TestModelLevelConstraintsErrorMessages(BaseConstraintsEnabledModelvsProject):
    @pytest.fixture(scope="class")
    def models(self):
        return {
            "my_model.sql": my_model_error_sql,
            "python_model.py": my_model_python_error,
            "constraints_schema.yml": model_schema_errors_yml,
        }

    def test__config_errors(self, project):

        results, log_output = run_dbt_and_capture(['run', '-s', 'my_model'], expect_pass=False)
        manifest = get_manifest(project.project_root)
        model_id = "model.test.my_model"
        my_model_config = manifest.nodes[model_id].config
        constraints_enabled_actual_config = my_model_config.constraints_enabled

        assert constraints_enabled_actual_config is True

        expected_materialization_error = "Materialization Error: {'materialization': 'view'}"
        expected_empty_data_type_error = "Columns with `data_type` Blank/Null Errors: {'date_day'}"
        assert expected_materialization_error in log_output
        assert expected_empty_data_type_error in log_output

    def test__python_errors(self, project):

        results, log_output = run_dbt_and_capture(['run', '-s', 'python_model'], expect_pass=False)
        manifest = get_manifest(project.project_root)
        model_id = "model.test.python_model"
        my_model_config = manifest.nodes[model_id].config
        constraints_enabled_actual_config = my_model_config.constraints_enabled

        assert constraints_enabled_actual_config is True

        expected_python_error = "Language Error: {'language': 'python'}"
        assert expected_python_error in log_output
