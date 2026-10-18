[CmdletBinding()]
param(
    [string]$BaseUrl = "http://127.0.0.1:8002"
)

$ErrorActionPreference = "Stop"

function Invoke-DemoApi {
    param(
        [Parameter(Mandatory)][string]$Path,
        [string]$Method = "GET",
        [hashtable]$Body,
        [hashtable]$Headers = @{}
    )

    $request = @{
        Uri = "$BaseUrl$Path"
        Method = $Method
        Headers = $Headers
        SkipHttpErrorCheck = $true
    }
    if ($null -ne $Body) {
        $request.ContentType = "application/json"
        $request.Body = ConvertTo-Json -InputObject $Body -Depth 12 -Compress
    }
    $response = Invoke-WebRequest @request
    $content = $null
    if ($response.Content) {
        $content = ConvertFrom-Json -InputObject $response.Content -AsHashtable
    }
    return @{ Status = [int]$response.StatusCode; Body = $content }
}

function Assert-Status {
    param($Response, [int]$Expected, [string]$Label)
    if ($Response.Status -ne $Expected) {
        throw "$Label returned HTTP $($Response.Status), expected ${Expected}: $($Response.Body | ConvertTo-Json -Depth 8 -Compress)"
    }
}

$commander = @{ "X-Demo-Role" = "commander" }
$baseManager = @{ "X-Demo-Role" = "base"; "X-Demo-Base" = "alpha" }
$logistics = @{ "X-Demo-Role" = "logistics" }

# Start from the FD001-specific demo seed. This resets only this server's
# in-memory state; do not point the script at a shared or production server.
$r = Invoke-DemoApi -Path "/api/demo/reset" -Method POST -Headers $commander
Assert-Status $r 200 "FD001 demo reset"

$r = Invoke-DemoApi -Path "/api/health/A21"
Assert-Status $r 200 "A21 health"
$health = $r.Body
if ($health.aircraft_id -ne "A21" -or
    $health.provider -ne "fd001-random-forest" -or
    $health.model_version -ne "cmapss-fd001-rf-v1" -or
    $health.rul_unit -ne "cycles" -or
    $null -ne $health.failure_probability -or
    $health.subsystem -ne $null -or
    $health.is_synthetic -ne $true) {
    throw "A21 did not return the expected cycle-only FD001 contract"
}

$r = Invoke-DemoApi -Path "/api/maintenance/events"
Assert-Status $r 200 "List predicted events"
$event = @($r.Body | Where-Object { $_.aircraft_id -eq "A21" -and $_.status -eq "OPEN" } | Select-Object -First 1)[0]
if ($null -eq $event) { throw "No open A21 prediction event was created" }
if ($event.aircraft_id -ne "A21" -or $event.subsystem -ne $null -or $event.predicted_time -ne $null -or $event.rul_unit -ne "cycles") {
    throw "A21 event contains subsystem or hour/deadline information not supplied by FD001"
}

$r = Invoke-DemoApi -Path "/api/maintenance/work-orders"
Assert-Status $r 200 "List initial work orders"
if (@($r.Body).Count -ne 0) { throw "FD001 reset retained mock-seeded work orders" }
$r = Invoke-DemoApi -Path "/api/inventory"
Assert-Status $r 200 "Read inventory"
$inventoryBefore = @($r.Body)
$stockBefore = @{}
foreach ($line in $inventoryBefore) {
    $stockBefore["$($line.base_id)|$($line.part_number)"] = [int]$line.quantity
}
$r = Invoke-DemoApi -Path "/api/fleet/overview"
Assert-Status $r 200 "Initial fleet overview"
$fleetBefore = $r.Body

# Prediction is connected, but it only creates/updates an event. It does not
# triage or create a work order. A Commander cannot invoke this Base action.
$r = Invoke-DemoApi -Path "/api/aircraft/A21/predict" -Method POST -Headers $commander
Assert-Status $r 403 "Wrong-role prediction request"
$historyBefore = (Invoke-DemoApi -Path "/api/predictions/A21/history").Body.count
$firstPrediction = Invoke-DemoApi -Path "/api/aircraft/A21/predict" -Method POST -Headers $baseManager
Assert-Status $firstPrediction 200 "First A21 prediction ingestion"
$secondPrediction = Invoke-DemoApi -Path "/api/aircraft/A21/predict" -Method POST -Headers $baseManager
Assert-Status $secondPrediction 200 "Repeated A21 prediction ingestion"
if ($firstPrediction.Body.predicted_maintenance_event.id -ne $event.id -or
    $secondPrediction.Body.predicted_maintenance_event.id -ne $event.id) {
    throw "Repeated ingestion did not reuse the unresolved A21 event"
}
if ($firstPrediction.Body.work_order_created -or $secondPrediction.Body.work_order_created) {
    throw "Prediction ingestion unexpectedly created a work order"
}
$historyAfter = (Invoke-DemoApi -Path "/api/predictions/A21/history").Body.count
if ($historyAfter -ne ($historyBefore + 2)) { throw "Expected one recorded history row per prediction call" }

# FD001 has no subsystem mapping. A human explicitly chooses a catalog part.
$badPart = Invoke-DemoApi -Path "/api/maintenance/events/$($event.id)/work-order" `
    -Method POST -Headers $baseManager -Body @{ required_component = "NOT-A-PART"; actor = "base" }
Assert-Status $badPart 409 "Unknown component rejection"
$triageBody = @{ required_component = "HP-204"; actor = "base" }
$firstTriage = Invoke-DemoApi -Path "/api/maintenance/events/$($event.id)/work-order" `
    -Method POST -Headers $baseManager -Body $triageBody
Assert-Status $firstTriage 200 "A21 human triage"
$secondTriage = Invoke-DemoApi -Path "/api/maintenance/events/$($event.id)/work-order" `
    -Method POST -Headers $baseManager -Body $triageBody
Assert-Status $secondTriage 200 "Repeated A21 triage"
$workOrder = $firstTriage.Body
if ($workOrder.id -ne $secondTriage.Body.id) { throw "Repeated triage created a second work order" }
if ($workOrder.required_component -ne "HP-204" -or
    $workOrder.aircraft_id -ne "A21" -or
    $workOrder.predicted_event_id -ne $event.id -or
    $workOrder.rul_unit -ne "cycles" -or
    $null -ne $workOrder.required_by_flight_hours) {
    throw "Work order lost the selected component or mislabeled cycle RUL as hours"
}

$r = Invoke-DemoApi -Path "/api/resources/search/$($workOrder.id)"
Assert-Status $r 200 "Resource search"
$resourceSearch = $r.Body
$r = Invoke-DemoApi -Path "/api/work-orders/$($workOrder.id)/recommendation"
Assert-Status $r 200 "Candidate evaluation"
$evaluation = $r.Body
if ($resourceSearch.required_component -ne "HP-204" -or
    $evaluation.required_component -ne "HP-204" -or
    $null -eq $evaluation.recommended) {
    throw "The chosen catalog component has no feasible recommendation"
}
foreach ($candidate in $evaluation.candidates) {
    $key = "$($candidate.base_id)|HP-204"
    if (-not $stockBefore.ContainsKey($key) -or
        [int]$candidate.quantity_available -gt $stockBefore[$key] -or
        [int]$candidate.condition_pct -lt [int]$candidate.min_condition_pct) {
        throw "Candidate $($candidate.base_id) does not agree with stock/condition constraints"
    }
}

# Rejection is presently an audit record, not a terminal decision state.
# Verify it moves no stock and creates no transfer; explicit later approval is
# currently allowed against the same work order.
$transferCountBeforeReject = @((Invoke-DemoApi -Path "/api/transfers").Body).Count
$inventoryBeforeReject = ConvertTo-Json -InputObject @( (Invoke-DemoApi -Path "/api/inventory").Body ) -Depth 8 -Compress
$r = Invoke-DemoApi -Path "/api/recommendations/A21/reject" -Method POST -Headers $commander `
    -Body @{ actor = "commander"; reason = "Readiness audit rejection" }
Assert-Status $r 200 "Reject recommendation"
if (-not $r.Body.rejected) { throw "Reject endpoint did not acknowledge the action" }
$transferCountAfterReject = @((Invoke-DemoApi -Path "/api/transfers").Body).Count
$inventoryAfterReject = ConvertTo-Json -InputObject @( (Invoke-DemoApi -Path "/api/inventory").Body ) -Depth 8 -Compress
if ($transferCountAfterReject -ne $transferCountBeforeReject -or
    $inventoryAfterReject -ne $inventoryBeforeReject) {
    throw "Recommendation rejection unexpectedly created a transfer or moved inventory"
}

$r = Invoke-DemoApi -Path "/api/work-orders/$($workOrder.id)/recommendation/approve" `
    -Method POST -Headers $commander -Body @{ actor = "commander" }
Assert-Status $r 200 "Approval after audit-only rejection"
$transfer = $r.Body.transfer
if ($transfer.status -ne "IN_TRANSIT" -or $transfer.work_order_id -ne $workOrder.id) {
    throw "Commander approval did not start the expected work-order transfer"
}
$sourceKey = "$($transfer.source_base)|$($transfer.part_number)"
$destKey = "$($transfer.dest_base)|$($transfer.part_number)"
$inventory = @( (Invoke-DemoApi -Path "/api/inventory").Body )
$sourceAfterDispatch = [int](@($inventory | Where-Object { "$($_.base_id)|$($_.part_number)" -eq $sourceKey })[0].quantity)
$destAfterDispatch = [int](@($inventory | Where-Object { "$($_.base_id)|$($_.part_number)" -eq $destKey })[0].quantity)
if ($sourceAfterDispatch -ne ($stockBefore[$sourceKey] - 1) -or $destAfterDispatch -ne $stockBefore[$destKey]) {
    throw "Dispatch did not decrement only the donor inventory"
}

$r = Invoke-DemoApi -Path "/api/transfers/$($transfer.id)/receive?actor=logistics" -Method POST -Headers $logistics
Assert-Status $r 200 "Logistics receipt"
if ($r.Body.status -ne "RECEIVED") { throw "Transfer was not received" }
$inventoryReceivedSnapshot = ConvertTo-Json -InputObject @( (Invoke-DemoApi -Path "/api/inventory").Body ) -Depth 8 -Compress
$repeatApproval = Invoke-DemoApi -Path "/api/work-orders/$($workOrder.id)/recommendation/approve" `
    -Method POST -Headers $commander -Body @{ actor = "commander" }
Assert-Status $repeatApproval 400 "Repeated approval after receipt"
if (@((Invoke-DemoApi -Path "/api/transfers").Body).Count -ne ($transferCountBeforeReject + 1) -or
    (ConvertTo-Json -InputObject @( (Invoke-DemoApi -Path "/api/inventory").Body ) -Depth 8 -Compress) -ne $inventoryReceivedSnapshot) {
    throw "Post-receipt approval created a duplicate transfer or moved inventory"
}
$inventory = @( (Invoke-DemoApi -Path "/api/inventory").Body )
$destAfterReceipt = [int](@($inventory | Where-Object { "$($_.base_id)|$($_.part_number)" -eq $destKey })[0].quantity)
if ($destAfterReceipt -ne ($stockBefore[$destKey] + 1)) { throw "Receipt did not increment destination inventory" }

$start = Invoke-DemoApi -Path "/api/maintenance/work-orders/$($workOrder.id)/start?actor=base" -Method POST -Headers $baseManager
Assert-Status $start 200 "Base maintenance start"
if ($start.Body.status -ne "IN_PROGRESS") { throw "Maintenance did not enter IN_PROGRESS" }
$fleetDuring = (Invoke-DemoApi -Path "/api/fleet/overview").Body
$complete = Invoke-DemoApi -Path "/api/maintenance/work-orders/$($workOrder.id)/complete?actor=base" -Method POST -Headers $baseManager
Assert-Status $complete 200 "Base maintenance completion"
if ($complete.Body.status -ne "COMPLETED") { throw "Maintenance did not complete" }
$inventoryDone = @( (Invoke-DemoApi -Path "/api/inventory").Body )
$destAfterConsumption = [int](@($inventoryDone | Where-Object { "$($_.base_id)|$($_.part_number)" -eq $destKey })[0].quantity)
if ($destAfterConsumption -ne $stockBefore[$destKey]) { throw "Maintenance completion did not consume the received unit" }
$fleetAfter = (Invoke-DemoApi -Path "/api/fleet/overview").Body
$aircraftAfter = (Invoke-DemoApi -Path "/api/aircraft/A21").Body

[pscustomobject]@{
    aircraft_id = "A21"
    engine_id = $health.metadata.engine_id
    model_version = $health.model_version
    rul = $health.rul
    rul_unit = $health.rul_unit
    risk = $health.risk_level
    failure_probability = $health.failure_probability
    subsystem = $health.subsystem
    synthetic = $health.is_synthetic
    unauthorized_predict_http = 403
    repeated_prediction_event_id = $event.id
    prediction_history_count_before = $historyBefore
    prediction_history_count_after = $historyAfter
    repeated_triage_work_order_id = $workOrder.id
    operator_selected_component = $workOrder.required_component
    rejected_recommendation_transfer_count = $transferCountAfterReject
    repeated_approval_after_receipt_http = $repeatApproval.Status
    approved_transfer_id = $transfer.id
    transfer_source = $transfer.source_base
    transfer_destination = $transfer.dest_base
    source_stock_before = $stockBefore[$sourceKey]
    source_stock_after_dispatch = $sourceAfterDispatch
    destination_stock_after_receipt = $destAfterReceipt
    destination_stock_after_consumption = $destAfterConsumption
    maintenance_status = $complete.Body.status
    aircraft_status_after = $aircraftAfter.status
    fleet_available_before = $fleetBefore.available
    fleet_available_during = $fleetDuring.available
    fleet_available_after = $fleetAfter.available
    fleet_maintenance_during = $fleetDuring.maintenance
    fleet_maintenance_after = $fleetAfter.maintenance
    rejection_is_audit_only = $true
    approved_after_rejection = $true
} | ConvertTo-Json -Depth 8
