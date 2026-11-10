import graphene
from core import datetime, datetimedelta
from core.schema import OpenIMISMutation
from django.core.exceptions import ValidationError
from django.utils.translation import gettext as _

from program.apps import ProgramConfig
from program.models import Program


def _check_rights(user, perms, action):
    """Refuse an anonymous user, or a user without `perms`. An empty right list
    refuses everyone: a program mutation is never open by default."""
    if user is None or not getattr(user, "is_authenticated", False) \
            or not perms or not user.has_perms(perms):
        return [{'message': _("unauthorized"), 'detail': _("Not allowed to %s a program") % action}]
    return None

class ProgramInputType(OpenIMISMutation.Input):
    idProgram = graphene.String(required=False, read_only=True)
    nameProgram = graphene.String(required=True)
    validityDateFrom = graphene.Date(required=False)
    validityDateTo = graphene.Date(required=False)
    id = graphene.Int(required=False)
    code = graphene.String(required=True)

def update_or_create_program(data, user):
    if "client_mutation_id" in data:
        data.pop('client_mutation_id')
    if "client_mutation_label" in data:
        data.pop('client_mutation_label')
    program_id = data.pop('id') if 'id' in data else None
    if program_id:
        program = Program.objects.get(idProgram=program_id)
        [setattr(program, key, data[key]) for key in data]
    else:
        program = Program.objects.create(**data)
    program.save()
    return program
   
class CreateProgramMutation(OpenIMISMutation):
    """
    Create a new program
    """
    _mutation_module = "program"
    _mutation_class = "CreateProgramMutation"

    class Input(ProgramInputType):
        pass

    @classmethod
    def async_mutate(cls, user, **data):
        denied = _check_rights(user, ProgramConfig.gql_mutation_programs_add_perms, "create")
        if denied:
            return denied
        try:
            data.pop('id', None)  # create never targets an existing program
            update_or_create_program(data, user)
            return None
        except Exception as exc:
            return [
                    {
                        'message': _("Failed to create program"),
                        'detail': str(exc)
                    }
                ]

class UpdateProgramMutation(OpenIMISMutation):
    """
    Update a program
    """
    _mutation_module = "program"
    _mutation_class = "UpdateProgramMutation"

    class Input(ProgramInputType):
        pass

    @classmethod
    def async_mutate(cls, user, **data):
        denied = _check_rights(user, ProgramConfig.gql_mutation_programs_edit_perms, "update")
        if denied:
            return denied
        try:
            update_or_create_program(data, user)
            return None
        except Exception as exc:
            return [
                {
                    'message': _("Failed to update program"),
                    'detail': str(exc)
                }
            ]

class DeleteProgramMutation(OpenIMISMutation):
    """
    Delete program (update validityDateTo)
    """

    class Input(ProgramInputType):
        pass

    _mutation_module = "program"
    _mutation_class = "DeleteProgramMutation"

    @classmethod
    def async_mutate(cls, user, **data):
        denied = _check_rights(user, ProgramConfig.gql_mutation_programs_delete_perms, "delete")
        if denied:
            return denied
        try:
            yesterday = datetime.datetime.now() - datetimedelta(days=1)
            if "nameProgram" in data:
                data.pop("nameProgram")
            data['validityDateTo'] = yesterday
            update_or_create_program(data, user)
            return None
        except Exception as exc:
            return [
                {
                    'message': _("Failed to delete program"),
                    'detail': str(exc)
                }
            ]
