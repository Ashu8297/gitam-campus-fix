import { AlertTriangle, AlertCircle, ArrowDown } from "lucide-react";
import { STATUS_LABEL } from "../utils";

const P = {
  high: { label: "High", Icon: AlertTriangle },
  medium: { label: "Medium", Icon: AlertCircle },
  low: { label: "Low", Icon: ArrowDown },
};

// Colour + icon + text, so priority never relies on colour alone.
export function PriorityBadge({ priority }) {
  const { label, Icon } = P[priority];
  return (
    <span className={`badge prio-${priority}`}>
      <Icon size={13} aria-hidden /> {label}
    </span>
  );
}

export function StatusBadge({ status }) {
  return <span className={`badge st-${status}`}>{STATUS_LABEL[status]}</span>;
}
