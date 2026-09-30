"""The summary written at the end of a run."""

import os
from datetime import datetime


class Report:
    def __init__(self, mode, total, success_count, dead_letter_queue):
        self.mode = mode
        self.total = total
        self.success_count = success_count
        self.dead_letter_queue = dead_letter_queue

    def build_text(self):
        verb = "moved" if self.mode == "move" else "copied"
        lines = [
            "Image sorting report",
            f"Date:        {datetime.now():%Y-%m-%d %H:%M:%S}",
            f"Mode:        {self.mode}",
            f"Total found: {self.total}",
            f"Succeeded:   {self.success_count} {verb}",
            f"Failed:      {len(self.dead_letter_queue)}",
        ]
        if self.dead_letter_queue:
            lines.append("")
            lines.append("Failed images:")
            for path, reason in self.dead_letter_queue:
                lines.append(f"  [{reason}] {path}")
        return "\n".join(lines) + "\n"

    def save(self, output_dir):
        """Print the report and save it as a text file in the output folder. Returns the file path."""
        text = self.build_text()
        print()
        print(text)

        filename = f"report_{datetime.now():%Y%m%d_%H%M%S}.txt"
        report_path = os.path.join(output_dir, filename)
        with open(report_path, "w") as f:
            f.write(text)
        print(f"Report saved to {report_path}")
        return report_path
