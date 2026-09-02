from datetime import date, timedelta

from conftest import ADMIN_ACTOR_ID, ESTABLISHMENT_ID, MR_PRODUCT_ID, UNIT_ID
from fastapi.testclient import TestClient


def command_headers(headers: dict[str, str], key: str) -> dict[str, str]:
    return {**headers, "Idempotency-Key": key}


def create_customer(client: TestClient, headers: dict[str, str]) -> dict[str, object]:
    response = client.post(
        "/api/v1/crm/companies",
        headers=command_headers(headers, "service-customer-001"),
        json={
            "legal_name": "Cliente de Serviços sintético Ltda.",
            "trade_name": "Cliente Serviços",
            "business_unit_ids": [str(UNIT_ID)],
            "contacts": [
                {
                    "kind": "email",
                    "label": "financeiro",
                    "value": "financeiro-servicos@example.test",
                    "is_primary": True,
                }
            ],
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def create_contract(
    client: TestClient, headers: dict[str, str], customer: dict[str, object]
) -> dict[str, object]:
    today = date.today().isoformat()
    created = client.post(
        "/api/v1/contracts",
        headers=command_headers(headers, "service-contract-001"),
        json={
            "business_unit_id": str(UNIT_ID),
            "customer_company_id": customer["id"],
            "internal_number": "CT-SERVICE-001",
            "signed_on": today,
            "start_date": today,
            "contract_type": "recurring_service",
        },
    )
    assert created.status_code == 201, created.text
    version = client.post(
        f"/api/v1/contracts/{created.json()['id']}/versions",
        headers=command_headers(headers, "service-contract-version-001"),
        json={
            "effective_from": today,
            "issuer_establishment_id": str(ESTABLISHMENT_ID),
            "currency": "BRL",
            "billing_frequency": "monthly",
            "pricing_model": "monthly",
            "amount": "900.00",
            "billing_day": 10,
            "payment_terms_days": 15,
            "change_type": "initial",
            "change_reason": "Configuração inicial sintética",
            "source": "api",
            "services": [
                {
                    "product_service_id": str(MR_PRODUCT_ID),
                    "contractual_description": "Serviço recorrente com contrato",
                    "quantity": "1.000",
                    "unit_amount": "900.00",
                    "is_active": True,
                }
            ],
            "financial_contacts": [
                {
                    "contact_method_id": customer["contacts"][0]["id"],
                    "recipient_role": "primary",
                    "purpose": "billing",
                    "preferred_channel": "email",
                }
            ],
        },
    )
    assert version.status_code == 201, version.text
    return created.json()


def create_service(
    client: TestClient,
    headers: dict[str, str],
    customer_id: str,
    *,
    name: str,
    service_type: str,
    recurrence: str | None,
    contract_id: str | None = None,
    installment_total: int | None = None,
) -> dict[str, object]:
    response = client.post(
        "/api/v1/client-services",
        headers=headers,
        json={
            "business_unit_id": str(UNIT_ID),
            "customer_company_id": customer_id,
            "product_service_id": str(MR_PRODUCT_ID),
            "contract_id": contract_id,
            "name": name,
            "service_type": service_type,
            "recurrence": recurrence,
            "installment_total": installment_total,
            "start_date": date.today().isoformat(),
            "owner_actor_id": str(ADMIN_ACTOR_ID),
            "amount": "900.00",
            "currency": "BRL",
            "operational_lead_days": 5,
            "reminder_lead_days": 2,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def generate_and_bill(
    client: TestClient, headers: dict[str, str], service: dict[str, object], suffix: str
) -> tuple[dict[str, object], dict[str, object]]:
    generated = client.post(
        f"/api/v1/client-services/{service['id']}/occurrences/generate",
        headers=command_headers(headers, f"generate-occurrence-{suffix}"),
        json={"through": date.today().isoformat()},
    )
    assert generated.status_code == 200, generated.text
    occurrence = generated.json()["occurrences"][0]
    billing = client.post(
        f"/api/v1/client-services/{service['id']}/occurrences/{occurrence['id']}/billing-item",
        headers=command_headers(headers, f"bill-occurrence-{suffix}"),
    )
    assert billing.status_code == 201, billing.text
    replay = client.post(
        f"/api/v1/client-services/{service['id']}/occurrences/{occurrence['id']}/billing-item",
        headers=command_headers(headers, f"bill-occurrence-{suffix}"),
    )
    assert replay.json() == billing.json()
    return generated.json(), billing.json()


def test_contract_optional_occurrences_and_three_billing_origins(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    customer = create_customer(client, admin_headers)
    contract = create_contract(client, admin_headers, customer)
    with_contract = create_service(
        client,
        admin_headers,
        customer["id"],
        name="Recorrente com contrato",
        service_type="recurring",
        recurrence="monthly",
        contract_id=contract["id"],
    )
    recurring = create_service(
        client,
        admin_headers,
        customer["id"],
        name="Recorrente sem contrato",
        service_type="recurring",
        recurrence="quarterly",
    )
    one_time = create_service(
        client,
        admin_headers,
        customer["id"],
        name="Serviço pontual",
        service_type="one_time",
        recurrence=None,
    )

    assert with_contract["contract_id"] == contract["id"]
    assert recurring["contract_id"] is None
    assert one_time["contract_id"] is None

    generated_contract, billed_contract = generate_and_bill(
        client, admin_headers, with_contract, "contract"
    )
    generated_recurring, billed_recurring = generate_and_bill(
        client, admin_headers, recurring, "recurring"
    )
    generated_one_time, billed_one_time = generate_and_bill(
        client, admin_headers, one_time, "one-time"
    )

    assert generated_contract["next_occurrence_on"] is not None
    assert generated_recurring["next_occurrence_on"] is not None
    assert generated_one_time["next_occurrence_on"] is None
    assert billed_contract["source_type"] == "contract_recurring"
    assert billed_recurring["source_type"] == "service_recurring"
    assert billed_one_time["source_type"] == "service_one_time"
    assert len({billed_contract["id"], billed_recurring["id"], billed_one_time["id"]}) == 3
    one_time_item = client.get(
        f"/api/v1/billing/items/{billed_one_time['id']}", headers=admin_headers
    ).json()
    assert one_time_item["reference_type"] == "single"
    assert one_time_item["reference_label"] == "Única"
    assert one_time_item["origin_label"] == "Serviço avulso"
    assert one_time_item["snapshot"]["billing_reference"] == {
        "type": "single",
        "position": None,
        "total": None,
    }
    assert {billed_contract["status"], billed_recurring["status"], billed_one_time["status"]} == {
        "ready"
    }

    directory = client.get(
        f"/api/v1/client-services?customer_company_id={customer['id']}", headers=admin_headers
    )
    assert directory.status_code == 200
    assert len(directory.json()) == 3
    assert all(
        item["occurrences"][0]["billing_status"] == "item_created" for item in directory.json()
    )


def test_one_time_installments_create_explicit_distinct_occurrences_and_items(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    customer = create_customer(client, admin_headers)
    service = create_service(
        client,
        admin_headers,
        customer["id"],
        name="Estudo Ambiental",
        service_type="one_time",
        recurrence=None,
        installment_total=3,
    )
    assert service["installment_total"] == 3
    assert service["next_occurrence_on"] is None

    item_ids: list[str] = []
    start = date.today().replace(day=1)
    for number in (1, 2, 3):
        scheduled_for = start + timedelta(days=number - 1)
        generated = client.post(
            f"/api/v1/client-services/{service['id']}/occurrences/generate",
            headers=command_headers(admin_headers, f"installment-occurrence-{number}"),
            json={
                "scheduled_for": scheduled_for.isoformat(),
                "installment_number": number,
            },
        )
        assert generated.status_code == 200, generated.text
        occurrence = next(
            item
            for item in generated.json()["occurrences"]
            if item["installment_number"] == number
        )
        billed = client.post(
            f"/api/v1/client-services/{service['id']}/occurrences/{occurrence['id']}/billing-item",
            headers=command_headers(admin_headers, f"installment-billing-{number}"),
        )
        assert billed.status_code == 201, billed.text
        payload = billed.json()
        assert payload["source_type"] == "service_one_time"
        item = client.get(
            f"/api/v1/billing/items/{payload['id']}", headers=admin_headers
        ).json()
        assert item["origin_label"] == "Serviço avulso"
        assert item["reference_type"] == "installment"
        assert item["reference_position"] == number
        assert item["reference_total"] == 3
        assert item["reference_label"] == f"Parcela {number}/3"
        assert item["snapshot"]["billing_reference"] == {
            "type": "installment",
            "position": number,
            "total": 3,
        }
        item_ids.append(payload["id"])

    assert len(set(item_ids)) == 3
    detail = client.get(
        f"/api/v1/client-services?customer_company_id={customer['id']}",
        headers=admin_headers,
    )
    assert detail.status_code == 200
    saved_service = next(item for item in detail.json() if item["id"] == service["id"])
    assert sorted(item["installment_number"] for item in saved_service["occurrences"]) == [1, 2, 3]
    invalid = client.post(
        f"/api/v1/client-services/{service['id']}/occurrences/generate",
        headers=command_headers(admin_headers, "installment-occurrence-invalid"),
        json={"scheduled_for": (start + timedelta(days=4)).isoformat(), "installment_number": 4},
    )
    assert invalid.status_code == 422
