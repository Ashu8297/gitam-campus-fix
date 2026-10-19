import IssueFeed from "../components/IssueFeed";

export default function AdminIssues() {
  return (<><h2>Issue review &amp; assignment</h2>
    <p className="muted">Tick several reports for bulk actions. Each report is checked separately.</p>
    <IssueFeed selectable emptyText="No issues have been reported yet." /></>);
}
