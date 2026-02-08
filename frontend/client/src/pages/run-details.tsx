import { useMemo, useState } from "react";
import { useQuery, useMutation } from "@tanstack/react-query";
import { useRoute, Link } from "wouter";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { Skeleton } from "@/components/ui/skeleton";
import { RunStatusBadge, ProviderBadge } from "@/components/run-status-badge";
import { formatDateTime, formatDuration } from "@/lib/formatters";
import { apiRequest, queryClient } from "@/lib/queryClient";
import { useToast } from "@/hooks/use-toast";
import { ArrowLeft, CheckCircle, Trash2, Ban, Send, FileCode, AlertCircle, Edit3 } from "lucide-react";
import type { ChatResponse, Run } from "@shared/schema";

type ChatLine = { role: "user" | "assistant"; content: string; ts: string };

export default function RunDetails() {
  const [, params] = useRoute("/runs/:id");
  const runId = params?.id ?? "";
  const { toast } = useToast();
  const [activeTab, setActiveTab] = useState("overview");
  const [chatInput, setChatInput] = useState("");
  const [editInput, setEditInput] = useState("");
  const [chatHistory, setChatHistory] = useState<ChatLine[]>([]);

  const { data: run, isLoading } = useQuery<Run>({
    queryKey: ["/api/runs", runId],
    refetchInterval: (query) => {
      const data = query.state.data as Run | undefined;
      if (data && ["created", "planning", "approved", "applying", "destroying"].includes(data.status)) return 3000;
      return false;
    },
  });

  const refreshRun = () => queryClient.invalidateQueries({ queryKey: ["/api/runs", runId] });

  const approveMutation = useMutation({
    mutationFn: () => apiRequest("POST", `/api/runs/${runId}/approve`),
    onSuccess: () => {
      refreshRun();
      queryClient.invalidateQueries({ queryKey: ["/api/runs"] });
      toast({ title: "Run approved" });
    },
    onError: (err: Error) => toast({ title: "Approve failed", description: err.message, variant: "destructive" }),
  });

  const rejectMutation = useMutation({
    mutationFn: () => apiRequest("POST", `/api/runs/${runId}/reject`),
    onSuccess: () => {
      refreshRun();
      queryClient.invalidateQueries({ queryKey: ["/api/runs"] });
      toast({ title: "Run rejected" });
    },
    onError: (err: Error) => toast({ title: "Reject failed", description: err.message, variant: "destructive" }),
  });

  const destroyMutation = useMutation({
    mutationFn: () => apiRequest("POST", `/api/runs/${runId}/destroy`),
    onSuccess: () => {
      refreshRun();
      queryClient.invalidateQueries({ queryKey: ["/api/runs"] });
      toast({ title: "Destroy started" });
    },
    onError: (err: Error) => toast({ title: "Destroy failed", description: err.message, variant: "destructive" }),
  });

  const chatMutation = useMutation({
    mutationFn: async (message: string) => {
      const res = await apiRequest("POST", `/api/runs/${runId}/chat`, { message });
      return (await res.json()) as ChatResponse;
    },
    onSuccess: (data, message) => {
      const now = new Date().toISOString();
      setChatHistory((prev) => [
        ...prev,
        { role: "user", content: message, ts: now },
        { role: "assistant", content: data.response, ts: data.timestamp ?? now },
      ]);
      setChatInput("");
    },
    onError: (err: Error) => toast({ title: "Chat failed", description: err.message, variant: "destructive" }),
  });

  const editMutation = useMutation({
    mutationFn: () => apiRequest("POST", `/api/runs/${runId}/edit`, { message: editInput.trim() }),
    onSuccess: () => {
      refreshRun();
      queryClient.invalidateQueries({ queryKey: ["/api/runs"] });
      setEditInput("");
      toast({ title: "Run sent for replanning" });
    },
    onError: (err: Error) => toast({ title: "Edit failed", description: err.message, variant: "destructive" }),
  });

  const canChat = useMemo(() => run && ["planned", "reviewing"].includes(run.status), [run]);
  const canEdit = useMemo(() => run && ["planned", "reviewing"].includes(run.status), [run]);

  if (isLoading) {
    return (
      <div className="space-y-6 animate-fade-in">
        <Skeleton className="h-8 w-48" />
        <Skeleton className="h-32 w-full" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  if (!run) {
    return (
      <div className="flex flex-col items-center justify-center py-20">
        <AlertCircle className="h-12 w-12 text-muted-foreground/30 mb-4" />
        <h2 className="text-lg font-semibold">Run not found</h2>
        <Link href="/runs">
          <Button variant="outline" className="mt-4">
            <ArrowLeft className="h-4 w-4 mr-2" />
            Back to Runs
          </Button>
        </Link>
      </div>
    );
  }

  return (
    <div className="space-y-6 animate-fade-in" data-testid="page-run-details">
      <div className="flex items-start justify-between flex-wrap gap-3">
        <div className="flex items-center gap-3">
          <Link href="/runs">
            <Button variant="ghost" size="icon" data-testid="button-back-to-runs">
              <ArrowLeft className="h-4 w-4" />
            </Button>
          </Link>
          <div>
            <div className="flex items-center gap-2 flex-wrap">
              <h1 className="text-xl font-bold tracking-tight">Run Details</h1>
              <RunStatusBadge status={run.status} size="default" />
              <ProviderBadge provider={run.provider} />
            </div>
            <p className="text-xs text-muted-foreground mt-1">{run.created_at ? formatDateTime(run.created_at) : run.run_id}</p>
          </div>
        </div>

        <div className="flex gap-2 flex-wrap">
          {(run.status === "planned" || run.status === "reviewing") && (
            <Button onClick={() => approveMutation.mutate()} disabled={approveMutation.isPending} data-testid="button-approve-run">
              <CheckCircle className="h-4 w-4 mr-2" />
              Approve
            </Button>
          )}
          {!["completed", "failed", "destroyed"].includes(run.status) && (
            <Button variant="outline" onClick={() => rejectMutation.mutate()} disabled={rejectMutation.isPending} data-testid="button-reject-run">
              <Ban className="h-4 w-4 mr-2" />
              Reject
            </Button>
          )}
          {run.status === "completed" && (
            <Button variant="destructive" onClick={() => destroyMutation.mutate()} disabled={destroyMutation.isPending} data-testid="button-destroy-run">
              <Trash2 className="h-4 w-4 mr-2" />
              Destroy
            </Button>
          )}
        </div>
      </div>

      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList data-testid="tabs-run-details">
          <TabsTrigger value="overview" data-testid="tab-overview">Overview</TabsTrigger>
          <TabsTrigger value="plan" data-testid="tab-plan">Plan</TabsTrigger>
          <TabsTrigger value="chat" data-testid="tab-chat">Chat</TabsTrigger>
          <TabsTrigger value="edit" data-testid="tab-edit">Edit</TabsTrigger>
        </TabsList>

        <TabsContent value="overview" className="mt-4 space-y-4">
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-base">Request</CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-sm leading-relaxed">{run.request ?? "No request stored"}</p>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-base">Run Metadata</CardTitle>
            </CardHeader>
            <CardContent className="text-sm space-y-1">
              <p><strong>Run ID:</strong> {run.run_id}</p>
              <p><strong>Provider:</strong> {run.provider.toUpperCase()}</p>
              <p><strong>Status:</strong> {run.status}</p>
              <p><strong>Region:</strong> {run.region ?? "-"}</p>
              <p><strong>Duration:</strong> {formatDuration(run.duration ?? 0)}</p>
            </CardContent>
          </Card>

          {run.error ? (
            <Card className="border-red-500/20">
              <CardContent className="p-4">
                <div className="flex gap-3">
                  <AlertCircle className="h-5 w-5 text-red-500 shrink-0 mt-0.5" />
                  <div>
                    <p className="text-sm font-medium text-red-600 dark:text-red-400">Error</p>
                    <p className="text-sm text-muted-foreground mt-1">{run.error}</p>
                  </div>
                </div>
              </CardContent>
            </Card>
          ) : null}
        </TabsContent>

        <TabsContent value="plan" className="mt-4">
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-base">Terraform Configuration</CardTitle>
            </CardHeader>
            <CardContent>
              <Tabs defaultValue="main" className="w-full">
                <TabsList className="grid w-full grid-cols-4">
                  <TabsTrigger value="main">main.tf</TabsTrigger>
                  <TabsTrigger value="variables">variables.tf</TabsTrigger>
                  <TabsTrigger value="outputs">outputs.tf</TabsTrigger>
                  <TabsTrigger value="plan">Plan Output</TabsTrigger>
                </TabsList>
                
                <TabsContent value="main" className="mt-4">
                  {run.terraform_code?.main_tf ? (
                    <div className="rounded-md bg-muted p-4 overflow-x-auto">
                      <pre className="text-xs font-mono leading-relaxed whitespace-pre-wrap" data-testid="text-main-tf">
                        {run.terraform_code.main_tf}
                      </pre>
                    </div>
                  ) : (
                    <div className="flex flex-col items-center justify-center py-12 text-muted-foreground">
                      <FileCode className="h-10 w-10 mb-3 opacity-30" />
                      <p className="text-sm">No main.tf available</p>
                    </div>
                  )}
                </TabsContent>
                
                <TabsContent value="variables" className="mt-4">
                  {run.terraform_code?.variables_tf ? (
                    <div className="rounded-md bg-muted p-4 overflow-x-auto">
                      <pre className="text-xs font-mono leading-relaxed whitespace-pre-wrap" data-testid="text-variables-tf">
                        {run.terraform_code.variables_tf}
                      </pre>
                    </div>
                  ) : (
                    <div className="flex flex-col items-center justify-center py-12 text-muted-foreground">
                      <FileCode className="h-10 w-10 mb-3 opacity-30" />
                      <p className="text-sm">No variables.tf available</p>
                    </div>
                  )}
                </TabsContent>
                
                <TabsContent value="outputs" className="mt-4">
                  {run.terraform_code?.outputs_tf ? (
                    <div className="rounded-md bg-muted p-4 overflow-x-auto">
                      <pre className="text-xs font-mono leading-relaxed whitespace-pre-wrap" data-testid="text-outputs-tf">
                        {run.terraform_code.outputs_tf}
                      </pre>
                    </div>
                  ) : (
                    <div className="flex flex-col items-center justify-center py-12 text-muted-foreground">
                      <FileCode className="h-10 w-10 mb-3 opacity-30" />
                      <p className="text-sm">No outputs.tf available</p>
                    </div>
                  )}
                </TabsContent>
                
                <TabsContent value="plan" className="mt-4">
                  {run.plan_output ? (
                    <div className="rounded-md bg-muted p-4 overflow-x-auto">
                      <pre className="text-xs font-mono leading-relaxed whitespace-pre-wrap" data-testid="text-plan-output">
                        {run.plan_output}
                      </pre>
                    </div>
                  ) : (
                    <div className="flex flex-col items-center justify-center py-12 text-muted-foreground">
                      <FileCode className="h-10 w-10 mb-3 opacity-30" />
                      <p className="text-sm">No plan output available</p>
                    </div>
                  )}
                </TabsContent>
              </Tabs>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="chat" className="mt-4">
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-base">Ask About This Plan</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              {!canChat ? (
                <p className="text-sm text-muted-foreground">Chat is available only when status is `planned` or `reviewing`.</p>
              ) : null}

              <div className="space-y-3 max-h-[380px] overflow-auto">
                {chatHistory.length === 0 ? (
                  <p className="text-sm text-muted-foreground">No messages yet.</p>
                ) : (
                  chatHistory.map((line, idx) => (
                    <div key={`${line.ts}-${idx}`} className={`rounded-md p-3 text-sm ${line.role === "user" ? "bg-primary text-primary-foreground" : "bg-muted"}`}>
                      <p>{line.content}</p>
                    </div>
                  ))
                )}
              </div>

              <div className="flex gap-2">
                <Textarea
                  value={chatInput}
                  onChange={(e) => setChatInput(e.target.value)}
                  placeholder="Ask: what will this cost?"
                  rows={2}
                  data-testid="input-chat-message"
                />
                <Button
                  onClick={() => chatMutation.mutate(chatInput.trim())}
                  disabled={!canChat || !chatInput.trim() || chatMutation.isPending}
                  className="self-end"
                  data-testid="button-send-message"
                >
                  <Send className="h-4 w-4 mr-1" /> Send
                </Button>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="edit" className="mt-4">
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-base">Request Plan Changes</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              {!canEdit ? (
                <p className="text-sm text-muted-foreground">Editing is available only when status is `planned` or `reviewing`.</p>
              ) : null}
              <Textarea
                value={editInput}
                onChange={(e) => setEditInput(e.target.value)}
                placeholder="Example: change instance type to t3.small and add HTTPS"
                rows={4}
                data-testid="input-edit-message"
              />
              <Button
                onClick={() => editMutation.mutate()}
                disabled={!canEdit || !editInput.trim() || editMutation.isPending}
                data-testid="button-send-edit"
              >
                <Edit3 className="h-4 w-4 mr-2" />
                Submit Change Request
              </Button>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}