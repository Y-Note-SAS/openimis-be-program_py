from django.apps import AppConfig

MODULE_NAME = "program"

# Programs are managed from the product screens and Cameroon has no program right
# of its own: the program mutations default to the product rights. Override through
# ModuleConfiguration("program") when dedicated rights are created.
DEFAULT_CFG = {
    "gql_mutation_programs_add_perms": ["121002"],
    "gql_mutation_programs_edit_perms": ["121003"],
    "gql_mutation_programs_delete_perms": ["121004"],
}


class ProgramConfig(AppConfig):
    name = MODULE_NAME

    gql_mutation_programs_add_perms = []
    gql_mutation_programs_edit_perms = []
    gql_mutation_programs_delete_perms = []

    def __load_config(self, cfg):
        for field in cfg:
            if hasattr(ProgramConfig, field):
                setattr(ProgramConfig, field, cfg[field])

    def ready(self):
        from core.models import ModuleConfiguration

        cfg = ModuleConfiguration.get_or_default(MODULE_NAME, DEFAULT_CFG)
        self.__load_config(cfg)
