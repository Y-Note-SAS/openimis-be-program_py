"""
Security parity tests for program (Cameroon-only module, no reference equivalent).

The reference contract applied here is the generic openIMIS one
(core/tests/test_mutation_authentication.py + every module's mutations):
anonymous mutations are refused before anything is written, and a mutation needs a right
(a user without any right cannot create/update/delete). Programs also drive claim row
scope (claim.models.Claim.get_queryset filters on the user's *valid* programs), so an
unprivileged program expiry widens claim visibility.

Each test asserts the expected secure behaviour: a FAIL is a gap.
Tags: [REF <file>::<test>] generic pattern ported, [NEW] Cameroon specific.
"""
import json

from django.contrib.auth.models import AnonymousUser
from django.core.cache import cache

from core.models import MutationLog
from core.models.openimis_graphql_test_case import openIMISGraphQLTestCase
from core.test_helpers import (
    create_right_only_user,
    create_security_tree,
    create_test_interactive_user,
    get_test_token,
)
from program.models import Program
from program.test_helpers import create_test_program


class ProgramSecurityParityTests(openIMISGraphQLTestCase):
    @classmethod
    def setUpTestData(cls):
        cls.t = create_security_tree("SPG")
        cls.p1 = create_test_program(code="SPGP1", name="SPG program 1")
        cls.p2 = create_test_program(code="SPGP2", name="SPG program 2")
        cls.no_right = create_right_only_user("spgnoright", [], [cls.t.d1.id])
        cls.admin = create_test_interactive_user(username="spgadmin")  # superuser (control)

    def setUp(self):
        cache.clear()

    def _gql(self, user, query):
        headers = {"HTTP_AUTHORIZATION": f"Bearer {get_test_token(user)}"} if user else {}
        return json.loads(self.query(query, headers=headers).content)

    def _valid(self, program):
        program.refresh_from_db()
        return program.validityDateTo is None

    # ------------------------------------------------------------- anonymous (HTTP)
    def test_anonymous_create_program_http_refused(self):
        """[REF core/tests/test_mutation_authentication.py] anonymous createProgram over
        HTTP creates nothing and writes no MutationLog."""
        logs_before = MutationLog.objects.count()
        self._gql(None, 'mutation { createProgram(input: {clientMutationId: "spg-anon", '
                        'nameProgram: "SPG anon", code: "SPGANON"}) { internalId } }')
        self.assertFalse(Program.objects.filter(code="SPGANON").exists(),
                         "anonymous createProgram created a program")
        self.assertEqual(MutationLog.objects.count(), logs_before,
                         "anonymous mutation wrote a MutationLog")

    def test_anonymous_program_query_refused(self):
        """[REF core/schema.py OrderedDjangoFilterConnectionField: AuthenticationRequired]"""
        content = self._gql(None, 'query { program { edges { node { code } } } }')
        codes = {e["node"]["code"] for e in ((content.get("data") or {}).get("program") or {}).get("edges", [])}
        self.assertFalse(codes & {"SPGP1", "SPGP2"}, "anonymous program query returned programs")

    # ------------------------------------------------------------- rights (service level)
    def test_anonymous_create_refused(self):
        """[NEW] CreateProgramMutation.async_mutate refuses an anonymous user."""
        from program.gql_mutations import CreateProgramMutation
        CreateProgramMutation.async_mutate(AnonymousUser(), nameProgram="SPG anon2", code="SPGAN2")
        self.assertFalse(Program.objects.filter(code="SPGAN2").exists())

    def test_create_requires_right(self):
        """[REF generic: mutations check has_perms] a user without any right cannot
        create a program."""
        from program.gql_mutations import CreateProgramMutation
        CreateProgramMutation.async_mutate(self.no_right, nameProgram="SPG hack", code="SPGHACK")
        self.assertFalse(Program.objects.filter(code="SPGHACK").exists(),
                         "a user without rights created a program")

    def test_update_requires_right(self):
        """[REF generic: mutations check has_perms]"""
        from program.gql_mutations import UpdateProgramMutation
        UpdateProgramMutation.async_mutate(self.no_right, id=self.p1.idProgram,
                                           nameProgram="HACKED", code="SPGP1")
        self.p1.refresh_from_db()
        self.assertNotEqual(self.p1.nameProgram, "HACKED", "a user without rights renamed a program")

    def test_delete_requires_right(self):
        """[REF generic: mutations check has_perms]"""
        from program.gql_mutations import DeleteProgramMutation
        DeleteProgramMutation.async_mutate(self.no_right, id=self.p1.idProgram, code="SPGP1")
        self.assertTrue(self._valid(self.p1), "a user without rights expired a program")

    def test_create_control_admin(self):
        """[CONTROL] the same create call succeeds for an administrator."""
        from program.gql_mutations import CreateProgramMutation
        errors = CreateProgramMutation.async_mutate(self.admin, nameProgram="SPG ok", code="SPGOK")
        self.assertTrue(Program.objects.filter(code="SPGOK").exists(), errors)

    # ------------------------------------------------------------- impact on claim scope
    def test_unprivileged_program_expiry_does_not_widen_claim_scope(self):
        """[NEW] A claim user bound to program P1 sees only P1 claims. A user without any
        right must not be able to expire P1 and thereby lift that filter (Claim.get_queryset
        ignores expired programs, so the user would then see every program's claims)."""
        from claim.apps import ClaimConfig
        from claim.models import Claim
        from claim.test_helpers import create_test_claim
        from core.test_helpers import perm_ids
        from insuree.test_helpers import create_test_insuree
        from medical.models import Diagnosis

        icd = Diagnosis.objects.filter(validity_to__isnull=True).first()
        ins = create_test_insuree(custom_props={"current_village": self.t.v1},
                                  family_custom_props={"location": self.t.v1})
        for code, prog in (("SPG-C1", self.p1), ("SPG-C2", self.p2)):
            create_test_claim(custom_props={"code": code, "health_facility_id": self.t.hf1.id,
                                            "insuree_id": ins.id, "icd_id": icd.id, "program": prog})
        claim_user = create_right_only_user(
            "spgclaimuser", perm_ids(ClaimConfig.gql_query_claims_perms), [self.t.d1.id])
        self.p1.user.add(claim_user.i_user)

        def visible():
            cache.clear()
            return set(Claim.get_queryset(Claim.objects.filter(code__startswith="SPG-C"), claim_user)
                       .values_list("code", flat=True))

        self.assertEqual(visible(), {"SPG-C1"})  # program filter active
        from program.gql_mutations import DeleteProgramMutation
        DeleteProgramMutation.async_mutate(self.no_right, id=self.p1.idProgram, code="SPGP1")
        self.assertEqual(visible(), {"SPG-C1"},
                         "an unprivileged program expiry lifted the claim program filter")

    def test_claims_of_an_expired_program_stay_visible_to_its_users(self):
        """[NEW] Decision 2026-11-10: claims are linked to a program, so a user assigned to
        P1 keeps seeing the P1 claims after an administrator expires P1 -- and still only
        those (expiry neither hides them nor widens the filter)."""
        import datetime
        from claim.apps import ClaimConfig
        from claim.models import Claim
        from claim.test_helpers import create_test_claim
        from core.test_helpers import perm_ids
        from insuree.test_helpers import create_test_insuree
        from medical.models import Diagnosis

        icd = Diagnosis.objects.filter(validity_to__isnull=True).first()
        ins = create_test_insuree(custom_props={"current_village": self.t.v1},
                                  family_custom_props={"location": self.t.v1})
        for code, prog in (("SPG-E1", self.p1), ("SPG-E2", self.p2)):
            create_test_claim(custom_props={"code": code, "health_facility_id": self.t.hf1.id,
                                            "insuree_id": ins.id, "icd_id": icd.id, "program": prog})
        claim_user = create_right_only_user(
            "spgexpuser", perm_ids(ClaimConfig.gql_query_claims_perms), [self.t.d1.id])
        self.p1.user.add(claim_user.i_user)
        Program.objects.filter(pk=self.p1.pk).update(
            validityDateTo=datetime.date.today() - datetime.timedelta(days=2))
        cache.clear()
        visible = set(Claim.get_queryset(Claim.objects.filter(code__startswith="SPG-E"), claim_user)
                      .values_list("code", flat=True))
        self.assertEqual(visible, {"SPG-E1"})

    def test_user_without_program_is_not_restricted_by_program(self):
        """[CONTROL] current behaviour kept: a claim user with no program assignment is
        only scoped by location / health facility, not by program."""
        from claim.apps import ClaimConfig
        from claim.models import Claim
        from claim.test_helpers import create_test_claim
        from core.test_helpers import perm_ids
        from insuree.test_helpers import create_test_insuree
        from medical.models import Diagnosis

        icd = Diagnosis.objects.filter(validity_to__isnull=True).first()
        ins = create_test_insuree(custom_props={"current_village": self.t.v1},
                                  family_custom_props={"location": self.t.v1})
        for code, prog in (("SPG-N1", self.p1), ("SPG-N2", self.p2)):
            create_test_claim(custom_props={"code": code, "health_facility_id": self.t.hf1.id,
                                            "insuree_id": ins.id, "icd_id": icd.id, "program": prog})
        claim_user = create_right_only_user(
            "spgnoprog", perm_ids(ClaimConfig.gql_query_claims_perms), [self.t.d1.id])
        cache.clear()
        visible = set(Claim.get_queryset(Claim.objects.filter(code__startswith="SPG-N"), claim_user)
                      .values_list("code", flat=True))
        self.assertEqual(visible, {"SPG-N1", "SPG-N2"})

    def test_create_cannot_overwrite_an_existing_program(self):
        """[NEW] createProgram with an `id` must not update that program (the create right
        is not the edit right)."""
        from program.gql_mutations import CreateProgramMutation
        from product.apps import ProductConfig  # noqa: F401  (rights live with products)
        from program.apps import ProgramConfig
        creator = create_right_only_user(
            "spgcreator", [int(p) for p in ProgramConfig.gql_mutation_programs_add_perms], [self.t.d1.id])
        CreateProgramMutation.async_mutate(creator, id=self.p2.idProgram, nameProgram="OVERWRITTEN",
                                           code="SPGNEW")
        self.p2.refresh_from_db()
        self.assertNotEqual(self.p2.nameProgram, "OVERWRITTEN")
