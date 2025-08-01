import { useNavigate } from "react-router-dom";
import { useEffect, useMemo } from "react";
import { ColumnDef } from "@tanstack/react-table";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { MessageSquare } from "lucide-react";
import { useDispatch, useSelector } from 'react-redux';
import { fetchDemands } from '../../store/demand/demandSlice'

// Sample data
const demandRequests = [
  {
    id: 1,
    title: "Advanced Search Filters",
    description: "Users want more granular filtering options in search results",
    segment: "Enterprise",
    status: "High Priority",
    impact: 95,
    votes: 147,
    revenue: 250000,
    effort: "Medium",
    lastUpdated: "2 days ago",
    quotes: [
      "We desperately need better filters to find relevant content",
      "Current search is too basic for our enterprise needs",
    ],
  },
  {
    id: 2,
    title: "Mobile App Dark Mode",
    description: "Native dark mode support for mobile applications",
    segment: "Consumer",
    status: "In Progress",
    impact: 78,
    votes: 89,
    revenue: 50000,
    effort: "Low",
    lastUpdated: "5 hours ago",
    quotes: [
      "Dark mode is essential for night usage",
      "All modern apps should have dark mode",
    ],
  },
  {
    id: 3,
    title: "Real-time Collaboration",
    description: "Live document editing with multiple users simultaneously",
    segment: "Teams",
    status: "Research",
    impact: 87,
    votes: 203,
    revenue: 180000,
    effort: "High",
    lastUpdated: "1 week ago",
    quotes: [
      "Google Docs style collaboration would be game changing",
      "We need to edit documents together in real-time",
    ],
  },
  {
    id: 4,
    title: "API Rate Limiting Controls",
    description: "Allow developers to configure custom rate limits",
    segment: "Developers",
    status: "Backlog",
    impact: 65,
    votes: 45,
    revenue: 75000,
    effort: "Medium",
    lastUpdated: "3 days ago",
    quotes: [
      "Rate limits are too restrictive for our use case",
      "Need more flexibility in API consumption",
    ],
  },
];

const getStatusColor = (status: string) => {
  switch (status) {
    case "High Priority":
      return "bg-destructive/20 text-destructive";
    case "In Progress":
      return "bg-warning/20 text-warning";
    case "Research":
      return "bg-info/20 text-info";
    case "Backlog":
      return "bg-muted text-muted-foreground";
    default:
      return "bg-muted text-muted-foreground";
  }
};

const getImpactColor = (impact: number) => {
  if (impact >= 90) return "text-destructive";
  if (impact >= 70) return "text-warning";
  return "text-success";
};

export function DemandDashboard() {
  const navigate = useNavigate();
  const dispatch = useDispatch();
  const { list, loading, error } = useSelector((state) => state.demand);

  console.log("list", list)

  useEffect(() => {
    dispatch(fetchDemands());
  }, [dispatch]);

  const columns: ColumnDef<(typeof demandRequests)[0]>[] = useMemo(
    () => [
      {
        accessorKey: "title",
        header: "Feature Title",
        cell: ({ row }) => (
          <div>
            <div className="font-medium text-foreground">{row.original.title}</div>
            <div className="text-xs text-muted-foreground">{row.original.description}</div>
          </div>
        ),
      },
      {
        accessorKey: "segment",
        header: "Segment",
        cell: ({ row }) => (
          <Badge variant="outline" className="text-xs">
            {row.original.segment}
          </Badge>
        ),
      },
      {
        accessorKey: "status",
        header: "Status",
        cell: ({ row }) => (
          <Badge className={`${getStatusColor(row.original.status)} text-xs`}>
            {row.original.status}
          </Badge>
        ),
      },
      {
        accessorKey: "impact",
        header: "Impact",
        cell: ({ row }) => (
          <span className={`font-medium ${getImpactColor(row.original.impact)}`}>
            {row.original.impact}/100
          </span>
        ),
      },
      {
        accessorKey: "votes",
        header: "Votes",
        cell: ({ row }) => <span>{row.original.votes}</span>,
      },
      {
        accessorKey: "effort",
        header: "Effort",
        cell: ({ row }) => <span className="text-muted-foreground">{row.original.effort}</span>,
      },
      {
        id: "actions",
        header: "Action",
        cell: ({ row }) => (
          <Button
            size="sm"
            variant="outline"
            onClick={() => navigate(`/demand/feature-detail/${row.original.id}`)}
          >
            View
          </Button>
        ),
      },
    ],
    [navigate]
  );

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-bold text-foreground">Demand Dashboard</h2>
        <p className="text-muted-foreground">
          All feature requests collected across users, with actionable insights
        </p>
      </div>
      <div className="rounded-md border border-border overflow-x-auto">
        <Table>
          <TableHeader>
            <TableRow>
              {columns.map((column) => (
                <TableHead key={column.id ?? column.accessorKey}>
                  {typeof column.header === "string" ? column.header : column.header?.()}
                </TableHead>
              ))}
            </TableRow>
          </TableHeader>
          <TableBody>
            {demandRequests.map((row) => (
              <TableRow key={row.id}>
                {columns.map((column) => (
                  <TableCell key={column.id ?? column.accessorKey}>
                    {column.cell!({ row: { original: row } })}
                  </TableCell>
                ))}
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>

    </div>
  );
}
