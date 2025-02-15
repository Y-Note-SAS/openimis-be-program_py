import graphene
from core import ExtendedConnection, prefix_filterset
from core.schema import OrderedDjangoFilterConnectionField, DjangoObjectType
import datetime
from program.models import Program
import graphene_django_optimizer as gql_optimizer
from insuree import models as insuree_models
from policy import models as policy_models
from .gql_mutations import *
from django.db.models import Q

class ProgramGQLType(DjangoObjectType):
    class Meta:
        model = Program
        interfaces = (graphene.relay.Node,)
        filter_fields = {
            "nameProgram": ["exact", "icontains"],
            "code": ["exact", "icontains"]
        }
        connection_class = ExtendedConnection


class Query(graphene.ObjectType):
    program = OrderedDjangoFilterConnectionField(
        ProgramGQLType,
        diagnosisVariance=graphene.Int(),
        code_is_not=graphene.String(),
        orderBy=graphene.List(of_type=graphene.String),
        items=graphene.List(of_type=graphene.String),
        services=graphene.List(of_type=graphene.String),
        insureeId=graphene.Int(),
        visitDateFrom=graphene.Date(),
        hfId=graphene.Int(),
    )

    def resolve_program(self, info, **kwargs):
        query = Program.objects
        insuree_id = kwargs.get("insureeId", None)
        visit_date_from = kwargs.get("visitDateFrom", None)
        hfId = kwargs.get("hfId", None)
        today = datetime.datetime.now()
        if insuree_id and visit_date_from and hfId:
            program_facilies_ids = []
            program_facilies = Program.objects.filter(
                healthfacility=hfId).filter(
                validityDateFrom__lte=today).filter(
                Q(validityDateTo__isnull=True) | Q(validityDateTo__gte=today))
            for program_facility in program_facilies:
                program_facilies_ids.append(program_facility.idProgram)

            insuree = insuree_models.Insuree.objects.get(id=insuree_id)
            family_id = insuree.family_id
            policies = policy_models.Policy.objects.filter(
                family_id=family_id).filter(expiry_date__gte=visit_date_from).filter(
                    start_date__lte=visit_date_from).filter(status__in=([2,8])) 
            program_products_ids = []
            products_programs = []
            for policy in policies:
                if policy.product:
                    if policy.product.program_id:
                        products_programs.append(policy.product.program_id)
            programs_fetch = Program.objects.filter(
                idProgram__in=products_programs).filter(
                validityDateFrom__lte=today).filter(
                Q(validityDateTo__isnull=True) | Q(validityDateTo__gte=today))
            for prog in programs_fetch:
                program_products_ids.append(prog.idProgram)
            intersect = list(set(program_products_ids) & set(program_facilies_ids))
            query=query.filter(idProgram__in=intersect)
        else:
            lst = []
            program_lst = Program.objects.filter(
                validityDateFrom__lte=today).filter(
                Q(validityDateTo__isnull=True) | Q(validityDateTo__gte=today))
            for p in program_lst:
                lst.append(p.idProgram)
            query=query.filter(idProgram__in=lst)
        return gql_optimizer.query(query.all(), info)

class Mutation(graphene.ObjectType):
    create_program = CreateProgramMutation.Field()
    update_program = UpdateProgramMutation.Field()
    delete_program = DeleteProgramMutation.Field()