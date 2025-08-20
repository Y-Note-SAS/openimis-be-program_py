from program.models import Program
from django.utils import timezone

class DummyUser:
    def __init__(self):
      self.id_for_audit = 1 

def create_test_program(code="PRG001", name="Test Program", users=None, custom_props=None):
    """
    Creates a Program objet for testing.
    """
    if custom_props is None:
        custom_props = {}

    program = Program.objects.create(
        code=code,
        nameProgram=name,
        validityDateFrom=custom_props.get("validityDateFrom", timezone.now()),
        **custom_props
    )

    if users:
        program.user.set(users)

    return program
