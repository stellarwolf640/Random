def runAction(self, event, system, GetDatabaseID):
    
    missing = self.view.params.missing or []
    noResult = self.view.params.noResult or []
    trace = self.view.params.trace
    DatabaseID = GetDatabaseID.getDatabaseID(trace)

    # Only process stations < 310
    missing_small = [s for s in missing if s < 310]
    noResult_small = [s for s in noResult if s < 310]

    # Combine and dedupe; prefer 'missing' description if station in both lists
    stations_to_process = []
    seen = set()
    for s in missing_small:
        if s not in seen:
            stations_to_process.append((s, 'Manual Insert - Missing Station'))
            seen.add(s)
    for s in noResult_small:
        if s not in seen:
            stations_to_process.append((s, 'Manual Approve - No Result'))
            seen.add(s)

    # Nothing to do
    if not stations_to_process:
        system.perspective.closePopup(self.view.params.id)
        return

    now = system.date.now()
    inserted = []
    skipped = []

    try:
        for station, description in stations_to_process:
            # Get latest AttemptNo for this trace/station
            params_latest = {"TraceCode": trace, "Station": station}
            ds = system.db.runNamedQuery("GetLatestAttempt", params_latest)

            if ds.getRowCount() > 0:
                try:
                    latest_attempt = ds.getValueAt(0, 0)
                    attempt_no = int(latest_attempt) + 1
                except Exception:
                    attempt_no = 1
            else:
                attempt_no = 1

            # Prepare insert parameters
            insert_params = {
                "DatabaseID": DatabaseID,
                "Station": station,
                "CheckDescription": description,
                "CheckResult": 1,               # manual approval
                "TimeStamp": now,
                "TraceCode": trace,
                "AttemptNo": attempt_no,
                "ManualApprove": 1
            }

            # Execute insert
            system.db.runNamedQuery("InsertRackAxleCheckLog", insert_params)
            inserted.append(station)

    except Exception as e:
        # Log the error and keep the popup open so operator can retry
        system.util.getLogger("ManualApprove").error("Failed to insert manual approvals for trace {}: {}".format(trace, e))
        # Optionally show a small popup or message to the operator here
        # e.g., system.perspective.openPopup(...) or set a label text
        return

    # Optionally log success
    system.util.getLogger("ManualApprove").info("Inserted manual approvals for trace {}: {}".format(trace, inserted))

    # Close the confirmation popup
    system.perspective.closePopup(self.view.params.id)