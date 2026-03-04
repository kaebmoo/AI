"""
NT AI Assistant - Report Export Tool
=======================================
Export query results to Excel/CSV files.

Example tool demonstrating the tool system.
Add new tools by creating a new .py file in app/tools/ — auto-discovered.
"""

import os
import csv
import json
import logging
import tempfile
from datetime import datetime
from typing import Dict, List, Any, Optional

from app.tools.base import BaseTool

logger = logging.getLogger(__name__)


class ReportExportTool(BaseTool):
    """Export query result to Excel or CSV"""

    name = "report_export"
    description = "Export query result data to CSV file"
    description_th = "ส่งออกผลลัพธ์เป็นไฟล์ CSV"
    preferred_tier = "cheap"  # No AI needed

    async def execute(
        self,
        data: List[Dict[str, Any]] = None,
        format: str = "csv",
        filename: str = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """
        Export data to file.

        Args:
            data: List of row dicts from query result
            format: "csv" (xlsx requires openpyxl)
            filename: Custom filename (auto-generated if None)

        Returns:
            {"success": True, "file_path": str, "format": str, "row_count": int}
        """
        if not data:
            return {"success": False, "error": "No data to export"}

        if not filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"nt_report_{timestamp}.{format}"

        export_dir = os.path.join(tempfile.gettempdir(), "nt_reports")
        os.makedirs(export_dir, exist_ok=True)
        file_path = os.path.join(export_dir, filename)

        try:
            if format == "csv":
                return self._export_csv(data, file_path)
            else:
                return {"success": False, "error": f"Unsupported format: {format}"}
        except Exception as e:
            logger.error(f"Export failed: {e}")
            return {"success": False, "error": str(e)}

    def _export_csv(self, data: List[Dict], file_path: str) -> Dict[str, Any]:
        """Export to CSV"""
        if not data:
            return {"success": False, "error": "Empty data"}

        headers = list(data[0].keys())

        with open(file_path, 'w', newline='', encoding='utf-8-sig') as f:
            writer = csv.DictWriter(f, fieldnames=headers)
            writer.writeheader()
            writer.writerows(data)

        logger.info(f"Exported {len(data)} rows to {file_path}")
        return {
            "success": True,
            "file_path": file_path,
            "format": "csv",
            "row_count": len(data),
        }

    def get_tool_spec(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": {
                    "format": {
                        "type": "string",
                        "description": "Export format: csv",
                        "enum": ["csv"],
                    },
                    "filename": {
                        "type": "string",
                        "description": "Custom filename (optional)",
                    },
                },
                "required": [],
            },
        }
