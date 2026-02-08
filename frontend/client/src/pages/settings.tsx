import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { AlertTriangle, Save } from "lucide-react";

import { apiRequest, queryClient } from "@/lib/queryClient";
import { useToast } from "@/hooks/use-toast";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Skeleton } from "@/components/ui/skeleton";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import type { AdminActionResponse, AppSettings } from "@shared/schema";

export default function SettingsPage() {
  const { toast } = useToast();
  const [draft, setDraft] = useState<AppSettings | null>(null);
  const [deletePhrase, setDeletePhrase] = useState("");
  const [resetPhrase, setResetPhrase] = useState("");

  const { data, isLoading, isError } = useQuery<AppSettings>({
    queryKey: ["/api/settings"],
    refetchInterval: 30000,
  });

  useEffect(() => {
    if (data) setDraft(data);
  }, [data]);

  const saveMutation = useMutation({
    mutationFn: async (settings: AppSettings) => {
      const res = await apiRequest("PUT", "/api/settings", { settings });
      return res.json();
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["/api/settings"] });
      toast({ title: "Settings saved" });
    },
    onError: (err: Error) => toast({ title: "Save failed", description: err.message, variant: "destructive" }),
  });

  const deleteMutation = useMutation({
    mutationFn: async () => {
      const res = await apiRequest("POST", "/api/admin/delete-all-runs", { confirmation: deletePhrase });
      return (await res.json()) as AdminActionResponse;
    },
    onSuccess: (result) => {
      queryClient.invalidateQueries();
      setDeletePhrase("");
      toast({ title: "All runs deleted", description: `${result.workspaces_deleted} workspaces removed` });
    },
    onError: (err: Error) => toast({ title: "Delete failed", description: err.message, variant: "destructive" }),
  });

  const resetMutation = useMutation({
    mutationFn: async () => {
      const res = await apiRequest("POST", "/api/admin/reset-application", { confirmation: resetPhrase });
      return (await res.json()) as AdminActionResponse;
    },
    onSuccess: () => {
      queryClient.invalidateQueries();
      setResetPhrase("");
      toast({ title: "Application reset complete" });
    },
    onError: (err: Error) => toast({ title: "Reset failed", description: err.message, variant: "destructive" }),
  });

  const canSave = useMemo(() => !!draft && JSON.stringify(draft) !== JSON.stringify(data), [draft, data]);

  if (isLoading) {
    return (
      <div className="space-y-4" data-testid="page-settings">
        <Skeleton className="h-12 w-52" />
        <Skeleton className="h-[420px] w-full" />
      </div>
    );
  }

  if (isError || !draft) {
    return (
      <Card data-testid="page-settings">
        <CardContent className="p-10 text-center text-sm text-muted-foreground">Unable to load settings.</CardContent>
      </Card>
    );
  }

  const setNotification = (key: keyof AppSettings["notifications"], value: boolean) =>
    setDraft((prev) => (prev ? { ...prev, notifications: { ...prev.notifications, [key]: value } } : prev));

  const setSecurity = (key: keyof AppSettings["security"], value: number | boolean) =>
    setDraft((prev) => (prev ? { ...prev, security: { ...prev.security, [key]: value } } : prev));

  const setAdvanced = (key: keyof AppSettings["advanced"], value: boolean) =>
    setDraft((prev) => (prev ? { ...prev, advanced: { ...prev.advanced, [key]: value } } : prev));

  return (
    <div className="space-y-6 animate-fade-in" data-testid="page-settings">
      <div>
        <h1 className="text-4xl font-bold tracking-tight">Settings</h1>
        <p className="text-muted-foreground">Configure your Terraform Cloud Agent</p>
      </div>

      <Tabs defaultValue="notifications">
        <TabsList>
          <TabsTrigger value="general">General</TabsTrigger>
          <TabsTrigger value="providers">Providers</TabsTrigger>
          <TabsTrigger value="notifications">Notifications</TabsTrigger>
          <TabsTrigger value="security">Security</TabsTrigger>
          <TabsTrigger value="advanced">Advanced</TabsTrigger>
        </TabsList>

        <TabsContent value="general">
          <Card>
            <CardHeader><CardTitle>General</CardTitle></CardHeader>
            <CardContent className="space-y-4">
              <div>
                <Label>Application Name</Label>
                <Input
                  value={draft.general.app_name}
                  onChange={(e) =>
                    setDraft((prev) => (prev ? { ...prev, general: { ...prev.general, app_name: e.target.value } } : prev))
                  }
                />
              </div>
              <div>
                <Label>Auto Refresh (seconds)</Label>
                <Input
                  type="number"
                  value={draft.general.auto_refresh_seconds}
                  onChange={(e) =>
                    setDraft((prev) =>
                      prev
                        ? {
                            ...prev,
                            general: { ...prev.general, auto_refresh_seconds: Number(e.target.value || 0) },
                          }
                        : prev,
                    )
                  }
                />
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="providers">
          <Card>
            <CardHeader><CardTitle>Providers</CardTitle></CardHeader>
            <CardContent className="space-y-4">
              <div>
                <Label>Default Provider</Label>
                <Input value={draft.providers.default_provider.toUpperCase()} readOnly />
              </div>
              <div>
                <Label>AWS Region</Label>
                <Input
                  value={draft.providers.default_region_aws}
                  onChange={(e) =>
                    setDraft((prev) =>
                      prev
                        ? {
                            ...prev,
                            providers: { ...prev.providers, default_region_aws: e.target.value },
                          }
                        : prev,
                    )
                  }
                />
              </div>
              <div>
                <Label>GCP Region</Label>
                <Input
                  value={draft.providers.default_region_gcp}
                  onChange={(e) =>
                    setDraft((prev) =>
                      prev
                        ? {
                            ...prev,
                            providers: { ...prev.providers, default_region_gcp: e.target.value },
                          }
                        : prev,
                    )
                  }
                />
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="notifications">
          <Card>
            <CardHeader><CardTitle>Notification Preferences</CardTitle></CardHeader>
            <CardContent className="space-y-5">
              <div className="flex items-center justify-between"><span>Run Completed</span><Switch checked={draft.notifications.run_completed} onCheckedChange={(v) => setNotification("run_completed", v)} /></div>
              <div className="flex items-center justify-between"><span>Run Failed</span><Switch checked={draft.notifications.run_failed} onCheckedChange={(v) => setNotification("run_failed", v)} /></div>
              <div className="flex items-center justify-between"><span>Approval Required</span><Switch checked={draft.notifications.approval_required} onCheckedChange={(v) => setNotification("approval_required", v)} /></div>
              <div className="flex items-center justify-between"><span>Cost Alert</span><Switch checked={draft.notifications.cost_alert} onCheckedChange={(v) => setNotification("cost_alert", v)} /></div>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="security">
          <Card>
            <CardHeader><CardTitle>Security Policies</CardTitle></CardHeader>
            <CardContent className="space-y-4">
              <div className="flex items-center justify-between"><span>Require Approval</span><Switch checked={draft.security.require_approval} onCheckedChange={(v) => setSecurity("require_approval", v)} /></div>
              <div>
                <Label>Maximum Cost Per Run</Label>
                <Input
                  type="number"
                  value={draft.security.maximum_cost_per_run}
                  onChange={(e) => setSecurity("maximum_cost_per_run", Number(e.target.value || 0))}
                />
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="advanced">
          <div className="space-y-4">
            <Card>
              <CardHeader><CardTitle>Developer Options</CardTitle></CardHeader>
              <CardContent>
                <div className="flex items-center justify-between">
                  <span>Debug Mode</span>
                  <Switch checked={draft.advanced.debug_mode} onCheckedChange={(v) => setAdvanced("debug_mode", v)} />
                </div>
              </CardContent>
            </Card>

            <Card className="border-red-500/30">
              <CardHeader>
                <CardTitle className="text-red-500">Danger Zone</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="flex flex-wrap items-center justify-between gap-3 rounded-md border border-red-500/20 p-3">
                  <div>
                    <p className="font-medium">Delete All Runs</p>
                    <p className="text-sm text-muted-foreground">Permanently delete all run data and workspaces.</p>
                  </div>
                  <AlertDialog>
                    <AlertDialogTrigger asChild>
                      <Button variant="destructive">Delete All Runs</Button>
                    </AlertDialogTrigger>
                    <AlertDialogContent>
                      <AlertDialogHeader>
                        <AlertDialogTitle>Confirm Deletion</AlertDialogTitle>
                        <AlertDialogDescription>
                          Type <code>DELETE ALL RUNS</code> to continue.
                        </AlertDialogDescription>
                      </AlertDialogHeader>
                      <Input value={deletePhrase} onChange={(e) => setDeletePhrase(e.target.value)} />
                      <AlertDialogFooter>
                        <AlertDialogCancel>Cancel</AlertDialogCancel>
                        <AlertDialogAction
                          disabled={deletePhrase !== "DELETE ALL RUNS" || deleteMutation.isPending}
                          onClick={() => deleteMutation.mutate()}
                          className="bg-destructive text-destructive-foreground"
                        >
                          Confirm
                        </AlertDialogAction>
                      </AlertDialogFooter>
                    </AlertDialogContent>
                  </AlertDialog>
                </div>

                <div className="flex flex-wrap items-center justify-between gap-3 rounded-md border border-red-500/20 p-3">
                  <div>
                    <p className="font-medium">Reset Application</p>
                    <p className="text-sm text-muted-foreground">Delete runs and restore all settings to defaults.</p>
                  </div>
                  <AlertDialog>
                    <AlertDialogTrigger asChild>
                      <Button variant="destructive">
                        <AlertTriangle className="mr-2 h-4 w-4" />
                        Reset
                      </Button>
                    </AlertDialogTrigger>
                    <AlertDialogContent>
                      <AlertDialogHeader>
                        <AlertDialogTitle>Confirm Reset</AlertDialogTitle>
                        <AlertDialogDescription>
                          Type <code>RESET APPLICATION</code> to continue.
                        </AlertDialogDescription>
                      </AlertDialogHeader>
                      <Input value={resetPhrase} onChange={(e) => setResetPhrase(e.target.value)} />
                      <AlertDialogFooter>
                        <AlertDialogCancel>Cancel</AlertDialogCancel>
                        <AlertDialogAction
                          disabled={resetPhrase !== "RESET APPLICATION" || resetMutation.isPending}
                          onClick={() => resetMutation.mutate()}
                          className="bg-destructive text-destructive-foreground"
                        >
                          Confirm
                        </AlertDialogAction>
                      </AlertDialogFooter>
                    </AlertDialogContent>
                  </AlertDialog>
                </div>
              </CardContent>
            </Card>
          </div>
        </TabsContent>
      </Tabs>

      <Button onClick={() => draft && saveMutation.mutate(draft)} disabled={!canSave || saveMutation.isPending}>
        <Save className="mr-2 h-4 w-4" />
        Save Changes
      </Button>
    </div>
  );
}
