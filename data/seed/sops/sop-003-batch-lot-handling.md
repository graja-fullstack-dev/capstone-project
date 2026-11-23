# SOP-003 Batch and Lot Number Handling

Lot numbers follow the format LOT-NNNNN: the prefix LOT, a hyphen, and exactly five digits (for example LOT-88392).

Operators verify the lot number against the packaging details given by the reporter. Common typos such as "lot 88392" or "LOT88392" are normalized automatically to the standard format and the correction is shown to the operator. Lot numbers that cannot be normalized are rejected with an explicit message.

Multiple reports sharing one lot number are not merged. Each report keeps its own reference identifier so that lot-level trends can be reviewed by searching on the lot number.
