# Settle model costs from reported usage

Matrix Run Cost Budget uses model-specific token pricing and settles Cost Reservations from API-reported input, cached-input, and output usage. A response without usage keeps its reservation as Unknown Usage, while an explicitly unsent request releases it. This favors a conservative shared cap over falsely treating an uncertain API charge as free, while keeping completed Matrix Arms attributable and reconcilable.
