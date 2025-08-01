import React, { useState } from "react";
import { Card, CardContent } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from "@/components/ui/accordion";
import { ArrowLeft, X } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Input } from "@/components/ui/input";

const insights = [
    {
        company: "Sample Company B",
        user: "Sample User B",
        noteType: "Call with Head of Business Operations",
        time: "12:57 PM",
        content:
            "Biggest un-met need is two-factor authentication, which will be a hard requirement for them within the next 6 months",
    },
    {
        company: "Sample Company B",
        user: "Sample User B",
        noteType: "Customer call",
        time: "12:57 PM",
        content: "Finally, it would be great to be able to use rich formatting...",
    },
    {
        company: "Sample Company E",
        user: "Sample User A",
        noteType: "Customer call",
        time: "12:57 PM",
        content:
            "Do you guys have an estimate for how long we’ll have to wait for these two-factor authentication? I’m getting some pressure from our head of IT who’s pushing to switch to one of your competitors.",
    },
];

const marketAnalysisData = [
    {
        company: "ServiceNow",
        details: [
            "✔️ Full BPMN support",
            "✔️ Drag-and-drop workflow builder",
            "✔️ Integration with AI Ops",
            "✔️ SLA and approval policies support"
        ]
    },
    {
        company: "Freshservice",
        details: [
            "✔️ Basic automation rules",
            "➖ Limited conditional branching",
            "➖ No visual workflow builder",
            "✔️ Integrates with Freshchat"
        ]
    },
    {
        company: "Jira Service Management",
        details: [
            "✔️ Deep Jira issue workflow integration",
            "✔️ Automation rules via JQL",
            "➖ Learning curve for new users",
            "✔️ Strong ecosystem integrations"
        ]
    },
    {
        company: "ManageEngine",
        details: [
            "➖ Template-based workflows only",
            "➖ Limited branching logic",
            "✔️ SLA and notification automation",
            "➖ Manual effort for changes"
        ]
    },
    {
        company: "OneLens",
        details: [
            "✔️ AI-assisted dynamic workflows",
            "✔️ Real-time trigger customization",
            "✔️ Visual editor with smart suggestions",
            "✔️ Predictive routing support"
        ]
    }
];


export default function FeatureDetailPage() {
    const navigate = useNavigate()

    const [status, setStatus] = useState("In Progress");
    const [timeFrame, setTimeFrame] = useState("Q3 2025");
    const [priority, setPriority] = useState("High");
    const [tags, setTags] = useState(["workflow", "automation"]);
    const [newTag, setNewTag] = useState("");

    const removeTag = (tagToRemove) => {
        setTags(tags.filter((tag) => tag !== tagToRemove));
    };

    const addTag = () => {
        if (newTag.trim() && !tags.includes(newTag.trim())) {
            setTags([...tags, newTag.trim()]);
            setNewTag("");
        }
    };

    return (
        <div className="">
            <div className="flex items-center gap-4">
                <div className="mb-4">
                    <Button
                        variant="ghost"
                        className="flex items-center gap-2 text-sm text-gray-700 dark:text-white"
                        onClick={() => navigate(-1)}
                    >
                        <ArrowLeft className="w-4 h-4" />
                        Back
                    </Button>
                </div>
                <div>
                    <Badge className="bg-green-400 font-medium">Completed</Badge>
                    <h1 className="text-xl font-semibold mt-2 mb-4">Advance Workflow</h1>
                </div>
            </div>
            <hr className="bg-gray-300" />
            <div className="flex w-full h-screen">
                {/* Left Main Content */}
                <div className="w-2/3 p-6">
                    <div className="bg-transparent">
                        <div className="p-6 space-y-4 text-sm text-gray-700 dark:text-white">
                            <p>This is a Sample feature</p>
                            <p>
                                <strong>Features</strong> represent a plannable, completable work on the order of an epic.
                            </p>
                            <ul className="list-disc list-inside">
                                <li>Examples: Upload a file</li>
                            </ul>
                            <p>
                                Features like this one typically <strong>represent big ideas you have for your product</strong>. They can be <strong>defined around broad capabilities</strong> you'd like to enable, or <strong>user needs</strong> you'd like to address.
                            </p>
                            <p>
                                You can also add this feature as a card on your Portal to allow colleagues and customers to vote and provide feedback on it.
                            </p>
                            <div>
                                <span className="text-base">📚 Learn more</span>
                                <ul className="list-disc list-inside text-blue-600 underline">
                                    <li><a href="#">Support Article</a></li>
                                    <li><a href="#">Productboard Academy: Organize your work into a useful hierarchy</a></li>
                                </ul>
                            </div>
                        </div>
                    </div>
                </div>

                {/* Right Side Panel */}
                <div className="w-1/3 border-l-2 border-gray-300">
                    <Tabs defaultValue="insights" className="h-full pt-2 bg-transparent">
                        <TabsList className="flex bg-transparent justify-start px-4  gap-4">
                            <TabsTrigger value="insights">Detail <span className="ml-1 bg-blue-100 text-blue-700 px-2 py-0.5 rounded-full text-xs">4</span></TabsTrigger>
                            <TabsTrigger value="market">Market Analysis</TabsTrigger>
                            <TabsTrigger value="portal">Competitor</TabsTrigger>
                        </TabsList>
                        <Separator className="mt-2" />
                        <TabsContent value="insights" className="p-4 h-[calc(100%-56px)] overflow-hidden">
                            <ScrollArea className="h-full pr-2 ">

                                {/* Feature Meta Section */}
                                <div className="space-y-4 px-2">
                                    {/* Status */}
                                    <div className="flex flex-col space-y-1">
                                        <label className="text-sm font-medium text-gray-700 dark:text-white">Status</label>
                                        <Select value={status} onValueChange={setStatus}>
                                            <SelectTrigger className="w-full">
                                                <SelectValue placeholder="Select status" />
                                            </SelectTrigger>
                                            <SelectContent>
                                                <SelectItem value="Planned">Planned</SelectItem>
                                                <SelectItem value="In Progress">In Progress</SelectItem>
                                                <SelectItem value="Completed">Completed</SelectItem>
                                                <SelectItem value="Backlog">Backlog</SelectItem>
                                            </SelectContent>
                                        </Select>
                                    </div>

                                    {/* Time Frame */}
                                    <div className="flex flex-col space-y-1">
                                        <label className="text-sm font-medium text-gray-700 dark:text-white">Time Frame</label>
                                        <Select value={timeFrame} onValueChange={setTimeFrame}>
                                            <SelectTrigger className="w-full">
                                                <SelectValue placeholder="Select time frame" />
                                            </SelectTrigger>
                                            <SelectContent>
                                                <SelectItem value="Q3 2025">Q3 2025</SelectItem>
                                                <SelectItem value="Q4 2025">Q4 2025</SelectItem>
                                                <SelectItem value="2026">2026</SelectItem>
                                            </SelectContent>
                                        </Select>
                                    </div>

                                    {/* Tags */}
                                    <div className="flex flex-col px-2 space-y-4">
                                        <label className="text-sm font-medium text-gray-700 dark:text-white">Tags</label>
                                        <div className="flex flex-wrap gap-2 mb-4">
                                            {tags.map((tag, idx) => (
                                                <Badge
                                                    key={idx}
                                                    className="flex items-center gap-1 bg-blue-100 text-blue-800 rounded-full px-3 py-1"
                                                >
                                                    {tag}
                                                    <X
                                                        className="w-3 h-3 cursor-pointer"
                                                        onClick={() => removeTag(tag)}
                                                    />
                                                </Badge>
                                            ))}
                                        </div>
                                        <div className="flex items-center gap-2 mt-4">
                                            <Input
                                                value={newTag}
                                                onChange={(e) => setNewTag(e.target.value)}
                                                placeholder="Add a tag"
                                                className="w-full"
                                                onKeyDown={(e) => {
                                                    if (e.key === "Enter") {
                                                        e.preventDefault();
                                                        addTag();
                                                    }
                                                }}
                                            />
                                            <Button size="sm" onClick={addTag}>
                                                Add
                                            </Button>
                                        </div>
                                    </div>

                                    {/* Priority */}
                                    <div className="flex flex-col space-y-1">
                                        <label className="text-sm font-medium text-gray-700 dark:text-white">Priority</label>
                                        <Select value={priority} onValueChange={setPriority}>
                                            <SelectTrigger className="w-full">
                                                <SelectValue placeholder="Select priority" />
                                            </SelectTrigger>
                                            <SelectContent>
                                                <SelectItem value="High">High</SelectItem>
                                                <SelectItem value="Medium">Medium</SelectItem>
                                                <SelectItem value="Low">Low</SelectItem>
                                            </SelectContent>
                                        </Select>
                                    </div>
                                </div>
                            </ScrollArea>
                        </TabsContent>

                        <TabsContent value="market" className="p-4 h-[calc(100%-56px)] overflow-hidden">
                            <ScrollArea className="h-full pr-2 space-y-4">
                                <Accordion type="single" className="space-y-2">
                                    {marketAnalysisData.map((vendor, i) => (
                                        <AccordionItem value={`item-${i}`} key={i}>
                                            <AccordionTrigger>{vendor.company}</AccordionTrigger>
                                            <AccordionContent>
                                                <ul className="text-sm text-gray-700 dark:text-white">
                                                    {vendor.details.map((point, j) => (
                                                        <li key={j}>{point}</li>
                                                    ))}
                                                </ul>
                                            </AccordionContent>
                                        </AccordionItem>
                                    ))}
                                </Accordion>
                            </ScrollArea>
                        </TabsContent>
                        <TabsContent value="portal" className="p-4 h-[calc(100%-56px)] overflow-hidden">
                            <ScrollArea className="h-full pr-2 space-y-4">
                                <div className="space-y-3">
                                    {[
                                        { company: "Acme Corp", user: "John Doe", time: "2 days ago", status: "Requested" },
                                        { company: "Globex Inc.", user: "Emily Zhang", time: "1 week ago", status: "Urgent" },
                                        { company: "Umbrella Systems", user: "Raj Malhotra", time: "4 days ago", status: "Requested" },
                                        { company: "Initech", user: "Sarah Kim", time: "Just now", status: "Requested" },
                                        { company: "Cyberdyne", user: "Tom Lee", time: "Yesterday", status: "Critical" },
                                    ].map((item, i) => (
                                        <Card key={i} className="border hover:shadow-md transition-shadow">
                                            <CardContent className="p-4 flex items-center justify-between">
                                                <div>
                                                    <div className="font-medium text-gray-900 dark:text-white">{item.company}</div>
                                                    <div className="text-sm text-gray-600">
                                                        by {item.user} • <span className="text-gray-500">{item.time}</span>
                                                    </div>
                                                </div>
                                                <Badge
                                                    className={`text-xs px-3 py-1 rounded-full ${item.status === "Urgent"
                                                        ? "bg-red-100 text-red-800"
                                                        : item.status === "Critical"
                                                            ? "bg-yellow-100 text-yellow-800"
                                                            : "bg-blue-100 text-blue-800"
                                                        }`}
                                                >
                                                    {item.status}
                                                </Badge>
                                            </CardContent>
                                        </Card>
                                    ))}
                                </div>
                            </ScrollArea>
                        </TabsContent>

                    </Tabs>
                </div>
            </div>
        </div>
    );
}
