# SOP-007 Audit Trail and Record Keeping

The local audit trail is append-only and tamper-evident. Each entry stores a UTC timestamp, the acting user code, the action (for example CREATE, STATUS_CHANGE, CLOSE_REQUESTED, APPROVED, REJECTED, CIRCUIT_OPEN), the reference identifier, status before and after, and the names of fields involved.

Audit entries never contain free-text descriptions or any personal details. Entries are chained by hash so any alteration is detected by the chain verification on the Audit Log page. Audit entries cannot be edited or deleted through the application.
