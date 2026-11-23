# PawPal+ care knowledge base

These are the documents the care advisor searches before it suggests anything. Each file has a small header
and a body. An optional `## Tasks` section lists care tasks the advisor may suggest from that document:

```
- Title | minutes | priority | frequency | preferred time (HH:MM or blank) | keys: words, that, match
```

`keys` are the words used to tell whether an owner's existing task already covers that care item
(for example "feed", "meal" and "breakfast" all count as feeding). Tasks marked `high` are treated as
essential daily care when the advisor reviews a plan.

The guidance here is general and was written for this project. It is not veterinary advice, and the
advisor tells users to check with their vet for anything about their specific pet's health.
