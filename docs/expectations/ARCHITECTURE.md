# MIRAH / The Oracle — target architecture

Status: **architecture decided by Nigel on 20 October 2026; NYUAD approvals pending.** Based on the on-premises infrastructure specification v1.0 (16 October 2026). It supersedes the 20 October "University Hosting Proposal (Updated)", which proposed Claude/OpenAI as primary inference with no GPU. Go-live: 20 November 2026. Nothing below is purchased, installed or deployed.

## Final decisions — Nigel, 20 October 2026

| Decision | Detail |
| --- | --- |
| Model location | The model resides and runs on NYUAD servers. |
| Development | Development happens on a separate developer server, using dummy (synthetic) data only. |
| External services | Claude, OpenAI and Perplexity are available as a **controlled feature that can be turned on or off**, through the university gateway. On the developer server they may be used with dummy data. In production each stays off until its contract and Legal approval are in place. |
| The Oracle and MIRAH | **The Oracle is the brain that powers MIRAH**: the knowledge library, retrieval and model layer. MIRAH is the guided experience on top. |
| Learning | The Oracle trains on local input, with guardrails: library learning plus adapter training on consented, de-identified, reviewed input (see Learning below). |
| Features | The combination listed in [SCOPE.md](SCOPE.md): the base Oracle scope plus the MIRAH expansion. |
| Users | NYUAD staff. |
| Timing of use | Before, during and after the Lab, to capture data. |
| Go-live | 20 November 2026. |

Open points from this decision are listed in [SCOPE.md](SCOPE.md) §10.

The source documents (17-page specification v1.0, hosting paper v1.1, handoff v1.1) are not yet in this repository. Add them only after Nigel confirms they contain no participant data, personal data or confidential research.

## Decisions recorded

| Area | Decision | Status |
| --- | --- | --- |
| Primary inference | Locally hosted open-weight model on NYUAD GPU servers. Main: gpt-oss-120b. Fallback: Llama 3.3 70B (licence review needed). Qwen only if NYUAD Security permits Chinese-origin models. Final choice by week-1 test on MIRAH's own test set. | Proposed |
| External services | Perplexity (research), Claude and OpenAI are optional. Each stays **off** until its contract is signed and legal approves. All calls pass through one allowlisted gateway with user approval of the exact outbound text, automatic blocking of personal data, confidential research, partner IP and agreement-restricted data, and an app-level plus network-level kill switch. Outputs are marked unverified and never become knowledge or training data without curator approval. | Proposed |
| Learning — library | Curator-approved contributions become searchable immediately; deletion removes them from future answers. | Proposed, planned for go-live |
| Learning — adapter | Opt-in, consented, de-identified, reviewed examples train a LoRA adapter every 4 weeks, outside workshop hours. Each release needs quality, safety, privacy and memorisation tests and a named approver; rollback under 5 minutes. Withdrawn records are excluded on the next rebuild. Needs at least 500 approved examples; first release expected Dec–Feb, not at go-live. | Proposed |
| Hosting and data | All stored data, backups and recovery copies stay on the NYUAD campus. App and GPU servers have no internet access. | Proposed |
| Identity | NYU single sign-on with MFA; guests on expiring NYU sponsored accounts. | Proposed |
| Compliance | Expected UAE PDPL (Federal Decree-Law No. 45 of 2021), to be confirmed by Legal. DPIA, versioned per-purpose consent, self-service export and deletion cascading to indexes and training data, 1-year audit log. Formal research goes through NYUAD IRB separately. | Pending Legal |
| Voice | Excluded from first purchase; separate evaluation. | Deferred |

### Change from the 12 October paper

The 12 October architecture paper said participant data would not be used for training. On 12 October Nigel confirmed that learning from user input is in scope. The specification therefore adds consented, de-identified adapter training under the controls above. This is a material privacy change and needs Legal, privacy and (for research use) IRB confirmation before any training runs.

## Hardware — configuration B (recommended)

2 GPU servers (4 × 96 GB RTX PRO 6000 Blackwell Server Edition, or 4 × H200 NVL), each with a small helper GPU; 2 application/database servers (PostgreSQL primary and replica); 1 backup server (≥ 40 TB, immutable snapshots, ideally a second room); 2 × 25 GbE switches plus a management switch; UPS ≥ 15 kVA. About 10.8 kW peak. Option A is one GPU server on existing NYUAD VMs (no redundancy); option C adds capacity. No prices; every line needs a vendor quote. Some datasheet figures are unverified.

Sizing basis: 20 concurrent users + 50% headroom, 3 parallel model calls per turn in creative stages, so a worst burst of 90 requests. Latency targets: first token < 4 s, full answer < 18 s. Throughput is not benchmarked; benchmark in week 1.

## Software

Ubuntu 24.04 LTS, NVIDIA drivers and CUDA, vLLM, PostgreSQL + pgvector, S3-compatible object storage, multilingual-e5-large embeddings plus reranker, Microsoft Presidio, Hugging Face PEFT/TRL, MLflow, Squid allowlist proxy, OpenBao or Vault, Prometheus/Grafana/Loki, pgBackRest + restic. Podman/Docker with Ansible; Kubernetes only if NYUAD already runs it.

Network zones: DMZ reverse proxy → APP → DATA and GPU (no internet); EGRESS gateway only to allowlisted provider APIs; BACKUP pulls encrypted copies; MGMT via MFA bastion.

## Operations targets

Database RPO 15 minutes, files 24 hours; service restored in 4 hours on the surviving server; backups kept 35 days with restore tested before go-live and quarterly. Patch one server at a time, never during workshops. Running budget under USD 25k/year excluding staff and power; external-service caps at most USD 9.6k/year.

## Open decisions (requested from NYUAD by 20 October 2026)

1. Procurement: can in-stock GPU servers be delivered by about 7 November?
2. Security: are Chinese-origin open models permitted?
3. Data centre: maximum kW per rack (one rack or two)?
4. IT infrastructure: is a second room available for backup?
5. Security: can an independent penetration test be booked by 23 October (report by 13 November)?
6. Legal/privacy: confirm applicable data-protection rules and whether short approved questions may leave campus.
7. Sponsor: choose configuration A, B or C; name the service owner and model-release approver.

## Top risks

- GPU servers arrive late (critical).
- Application not ready: the existing demo is cloud-based and must be ported in about 3 weeks; this repository has no application source yet (critical).
- Slow legal approval for external services (go live local-only).
- Latency when 5 teams change stage together.
- Adapter memorises personal data.
