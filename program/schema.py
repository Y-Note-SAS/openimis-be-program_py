import graphene
from core import ExtendedConnection, prefix_filterset
from core.schema import OrderedDjangoFilterConnectionField, DjangoObjectType
import datetime
from program.models import Program
import graphene_django_optimizer as gql_optimizer
from claim.models import Claim
from contribution_plan.apps import ContributionPlanConfig
from contribution_plan.gql import PaymentPlanGQLType
from contribution_plan.models import PaymentPlan
from core.utils import append_validity_filter
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import PermissionDenied
from invoice.apps import InvoiceConfig
from invoice.gql.gql_types.bill_types import BillGQLType
from invoice.models import Bill, BillItem
from insuree import models as insuree_models
from policy import models as policy_models
from product.models import Product
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
    bill_by_program = OrderedDjangoFilterConnectionField(
        BillGQLType,
        program_id=graphene.Int(required=True),
        orderBy=graphene.List(of_type=graphene.String),
        dateValidFrom__Gte=graphene.DateTime(),
        dateValidTo__Lte=graphene.DateTime(),
        applyDefaultValidityFilter=graphene.Boolean(),
    )
    payment_plan_by_program = OrderedDjangoFilterConnectionField(
        PaymentPlanGQLType,
        program_id=graphene.Int(required=True),
        orderBy=graphene.List(of_type=graphene.String),
        dateValidFrom__Gte=graphene.DateTime(),
        dateValidTo__Lte=graphene.DateTime(),
        applyDefaultValidityFilter=graphene.Boolean(),
        showHistory=graphene.Boolean(),
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
                family_id=family_id).filter(
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

    def resolve_bill_by_program(self, info, program_id, **kwargs):
        if not info.context.user.has_perms(InvoiceConfig.gql_bill_search_perms):
            raise PermissionDenied(_("unauthorized"))

        claim_content_type = ContentType.objects.get_for_model(Claim)
        claim_ids = [
            str(claim_id)
            for claim_id in Claim.objects.filter(
                program_id=program_id,
                validity_to__isnull=True,
            ).values_list("id", flat=True)
        ]
        bill_ids = BillItem.objects.filter(
            is_deleted=False,
            line_type=claim_content_type,
            line_id__in=claim_ids,
        ).values_list("bill_id", flat=True)
        query = Bill.objects.filter(id__in=bill_ids, *append_validity_filter(**kwargs)).distinct()
        if InvoiceConfig.bill_user_filter:
            query = InvoiceConfig.bill_user_filter(query, info.context.user)
        return gql_optimizer.query(query, info)

    def resolve_payment_plan_by_program(self, info, program_id, **kwargs):
        if not info.context.user.has_perms(ContributionPlanConfig.gql_query_paymentplan_perms):
            raise PermissionDenied(_("unauthorized"))

        product_content_type = ContentType.objects.get_for_model(Product)
        product_ids = [
            str(product_id)
            for product_id in Product.objects.filter(
                program_id=program_id,
                validity_to__isnull=True,
            ).values_list("id", flat=True)
        ]
        query = PaymentPlan.objects.filter(
            benefit_plan_type=product_content_type,
            benefit_plan_id__in=product_ids,
            *append_validity_filter(**kwargs),
        )
        return gql_optimizer.query(query, info)

class Mutation(graphene.ObjectType):
    create_program = CreateProgramMutation.Field()
    update_program = UpdateProgramMutation.Field()
    delete_program = DeleteProgramMutation.Field()
