# Scientific Metadata

Shots, Datasets and Collections all carry `scientific_metadata`: a list of claims about what the record is or contains. The vocabulary is open, so you choose the names and values, and FDS records what you assert without inferring anything you did not.

```json
{
  "scientific_metadata": [
    {"name": "campaign", "value": "M9"},
    {"name": "plasma_current_max", "value": 550630.7, "unit": "A"},
    {"name": "flat_top", "value": true,
     "extent": {"dimension": "time", "start": 0.06, "end": 0.27, "unit": "s"}}
  ]
}
```

A property with an `extent` is an **annotation**: the same claim, localised on one named axis of the data. Everything else describes the record as a whole.

## Declaring a kind

`kind` says what a value *is*. It is optional, and it is the single most useful thing you can add, because it decides how the property can be filtered and how an interface presents it.

| `kind` | What it is | How it is filtered | How the reference UI presents it |
| --- | --- | --- | --- |
| `term` | A value drawn from a vocabulary | Equality, with `property` | Chips when there are few values, a searchable list when there are many |
| `quantity` | A magnitude on a scale, usually with a `unit` | Range, with `property_min` and `property_max` | A two-handled range control with number entry |
| `text` | Prose written for a person to read | Not filterable | Never shown in the filter |

```json
{"name": "campaign",           "value": "M9",     "kind": "term"}
{"name": "plasma_current_max", "value": 550630.7, "kind": "quantity", "unit": "A"}
{"name": "postshot_comment",   "value": "Good shot, lost vertical control at 0.4 s",
 "kind": "text"}
```

`kind` describes the value, not the control. You are not choosing chips over a dropdown: you are saying whether a value is a term, a magnitude or prose, and the interface follows from that together with how many distinct values exist. A `term` with six values and a `term` with nine hundred are declared identically.

## What each kind looks like

A **term** with few values is offered as chips, one row per property. Selecting two values of one property matches either of them; selecting values of two properties matches both.

```text
campaign        M5   M6   M7   M8   M9
current_range   400 kA   700 kA   1000 kA
```

A **term** with too many values to show at once becomes a row you open, with search and a count against each value. The threshold is 20 distinct values by default.

```text
>  objective                                     941 values

   [ conditioning                              ]
   PLASMA CONDITIONING                       412
   VESSEL CONDITIONING                        88
```

A **boolean** term is three states rather than two chips, because selecting `true` and `false` together would mean the same as selecting neither.

```text
pellets    [ any | yes | no ]
```

A **quantity** is bounded rather than picked from. Dragging snaps to round steps sized from the observed span; the number fields take any value.

```text
plasma_current_max                 -995,852 A to 1,418,442 A
    o===============================o
    [ -995852 ]  to  [ 1418442 ]  A
```

## If you do not declare a kind

FDS infers one from the values it can see. The inference is good enough that no provider is obliged to do anything, and it is documented here so you can tell when it will get you wrong.

It reads how many distinct values there are before it looks at their type:

- A handful of values that repeat is a `term`, **whether or not those values are numbers**.
- A number that differs on nearly every record is a `quantity`.
- Text that is close to unique per record is `text`.

The middle rule is the one worth knowing about. Consider a target current range with three settings, correctly stored as a number with a unit:

```json
{"name": "current_range", "value": 700, "unit": "kA"}
```

Reading the type first would call that a quantity and offer a slider across three points. Reading the cardinality first sees a vocabulary that happens to be numeric, which is what it is. Inference gets this right, but only because the values repeat: if your catalogue holds few enough records that a genuine measurement has not started repeating, inference will call it a term. Declaring `kind` removes the guess.

Prose is separated from a vocabulary by how often values recur, not by how long they are. A hundred-character objective reused a dozen times is a vocabulary; a fifty-character comment written once is not. Below about twenty records there is not enough evidence to tell, so cardinality alone decides.

## What never appears in a filter

Two things are left out, and both are deliberate.

**Prose.** A comment describes one record rather than classifying it, so an equality filter on it matches one record and no other. Declaring `kind: "text"` states this; otherwise it is inferred.

**Anything that cannot divide the scope.** If every record carries a property with the same single value, selecting it returns the scope unchanged. That the property holds of the whole catalogue is worth knowing, and it is shown on each record, but it is not a way to narrow anything. The same property on half the records is offered, because then it does divide them.

## Units and ordering

`unit` is reported for a property only when every record agrees on one. A name recorded in both `A` and `kA` has no single unit, so FDS says nothing rather than picking one of them.

`description` follows the same rule, so a client can explain a property beside its filter. Give every entry of a name the same `description` and it is reported; vary it and it is not.

Values sort numerically when they are numbers and alphabetically otherwise. This is a reason to keep a magnitude out of its value: `700` with `"unit": "kA"` sorts before `1000`, while the string `"700 kA"` sorts after `"1000 kA"`.

## Filtering

See [Finding annotated records](index.md#finding-annotated-records) for the query syntax, and [Discovering what to filter on](index.md#discovering-what-to-filter-on) for the endpoint that reports the kinds, counts and values described here.
