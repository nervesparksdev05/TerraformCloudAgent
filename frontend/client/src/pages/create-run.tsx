import { useMemo, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useLocation } from "wouter";
import { ArrowLeft, ArrowRight, Cloud, FileText, MessageSquare, Send } from "lucide-react";

import { apiRequest, queryClient } from "@/lib/queryClient";
import { useToast } from "@/hooks/use-toast";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Progress } from "@/components/ui/progress";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import type { CreateRunPayload, TemplateDefinition } from "@shared/schema";

const totalSteps = 4;

export default function CreateRun() {
  const [step, setStep] = useState(1);
  const [method, setMethod] = useState<"natural_language" | "template">("natural_language");
  const [request, setRequest] = useState("");
  const [selectedTemplate, setSelectedTemplate] = useState<string>("");
  const [provider, setProvider] = useState<"aws" | "gcp">("aws");
  const [region, setRegion] = useState("us-east-1");
  const [templateParams, setTemplateParams] = useState<Record<string, string>>({
    instance_type: "t3.micro",
    storage_size: "20",
    enable_monitoring: "true",
    backup_retention: "7",
  });
  const [, navigate] = useLocation();
  const { toast } = useToast();

  const { data: templates = [] } = useQuery<TemplateDefinition[]>({
    queryKey: ["/api/templates"],
    staleTime: 60_000,
  });

  const { data: regions = [] } = useQuery<Array<{ code: string; name: string; provider: string }>>({
    queryKey: [`/api/regions?provider=${provider}`],
    staleTime: 300_000, // 5 minutes
  });

  const createMutation = useMutation({
    mutationFn: async () => {
      const payload: CreateRunPayload = {
        provider,
        region,
        method,
        auto_approve: false,
      };
      if (method === "natural_language") {
        payload.request = request.trim();
      } else {
        payload.template_id = selectedTemplate;
        payload.template_inputs = { provider, region, ...templateParams };
      }
      const res = await apiRequest("POST", "/api/runs", payload);
      return res.json();
    },
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ["/api/runs"] });
      queryClient.invalidateQueries({ queryKey: ["/api/dashboard/overview?days=30"] });
      toast({ title: "Run created" });
      navigate(`/runs/${data.run_id}`);
    },
    onError: (err: Error) => {
      toast({ title: "Failed to create run", description: err.message, variant: "destructive" });
    },
  });

  const filteredTemplates = useMemo(
    () => templates.filter((template) => template.providers.includes(provider)),
    [templates, provider],
  );

  const stepTitle = ["Method", "Define", "Configure", "Review"][step - 1];
  const progress = (step / totalSteps) * 100;

  const canNext = useMemo(() => {
    if (step === 1) return true;
    if (step === 2) {
      if (method === "natural_language") return request.trim().length >= 10;
      return !!selectedTemplate;
    }
    if (step === 3) return !!provider && !!region;
    if (step === 4) return true;
    return false;
  }, [step, method, request, selectedTemplate, provider, region]);

  const selectedTemplateObj = templates.find((t) => t.id === selectedTemplate);

  return (
    <div className="mx-auto max-w-4xl space-y-6 animate-fade-in" data-testid="page-create-run">
      <div>
        <h1 className="text-5xl font-bold tracking-tight text-balance">Create Infrastructure</h1>
        <p className="text-muted-foreground text-lg">Deploy cloud resources with AI-powered automation</p>
      </div>

      <Card>
        <CardContent className="space-y-6 p-6">
          <div className="space-y-3">
            <div className="flex items-center justify-between text-sm">
              <span>
                Step {step} of {totalSteps}
              </span>
              <span>{Math.round(progress)}%</span>
            </div>
            <Progress value={progress} />
            <div className="grid grid-cols-4 text-sm text-muted-foreground">
              <span className={step >= 1 ? "text-foreground font-medium" : ""}>Method</span>
              <span className={step >= 2 ? "text-foreground font-medium" : ""}>Define</span>
              <span className={step >= 3 ? "text-foreground font-medium" : ""}>Configure</span>
              <span className={step >= 4 ? "text-foreground font-medium" : ""}>Review</span>
            </div>
          </div>

          {step === 1 && (
            <div className="space-y-4">
              <h2 className="text-2xl font-semibold">{stepTitle}</h2>
              <div className="grid gap-4 md:grid-cols-2">
                <button
                  type="button"
                  className={`rounded-lg border p-8 text-left transition ${method === "natural_language" ? "border-primary ring-1 ring-primary" : "hover-elevate"}`}
                  onClick={() => setMethod("natural_language")}
                >
                  <MessageSquare className="mb-4 h-8 w-8 text-primary" />
                  <p className="text-3xl font-semibold">Natural Language</p>
                  <p className="text-muted-foreground">Describe what you want in plain English</p>
                </button>
                <button
                  type="button"
                  className={`rounded-lg border p-8 text-left transition ${method === "template" ? "border-primary ring-1 ring-primary" : "hover-elevate"}`}
                  onClick={() => setMethod("template")}
                >
                  <FileText className="mb-4 h-8 w-8 text-primary" />
                  <p className="text-3xl font-semibold">Use Template</p>
                  <p className="text-muted-foreground">Start from a pre-built template</p>
                </button>
              </div>
            </div>
          )}

          {step === 2 && method === "natural_language" && (
            <div className="space-y-4">
              <h2 className="text-2xl font-semibold">Describe Your Infrastructure</h2>
              <Textarea
                value={request}
                onChange={(e) => setRequest(e.target.value)}
                placeholder="e.g., Create a web server with nginx on AWS with a PostgreSQL database..."
                rows={7}
                data-testid="textarea-infrastructure-request"
              />
              <div className="flex items-center justify-between text-sm text-muted-foreground">
                <span>{request.trim().length} characters</span>
                <span>{Math.max(0, 10 - request.trim().length)} more needed</span>
              </div>
              <div className="rounded-lg border p-3 bg-muted/30">
                <p className="text-sm font-medium mb-2">💡 Example Prompts:</p>
                <div className="space-y-1 text-xs text-muted-foreground">
                  <p>• "Deploy a scalable web application with load balancer and auto-scaling"</p>
                  <p>• "Create a managed PostgreSQL database with automated backups"</p>
                  <p>• "Set up a serverless API with Lambda functions and API Gateway"</p>
                  <p>• "Build a Kubernetes cluster with 3 worker nodes"</p>
                </div>
              </div>
            </div>
          )}

          {step === 2 && method === "template" && (
            <div className="space-y-4">
              <h2 className="text-2xl font-semibold">Choose a Template</h2>
              
              {/* Provider Filter Buttons */}
              <div className="flex items-center gap-3">
                <Label className="text-sm font-medium">Provider:</Label>
                <div className="flex gap-2">
                  <Button
                    type="button"
                    variant={provider === "aws" ? "default" : "outline"}
                    size="sm"
                    onClick={() => {
                      setProvider("aws");
                      setRegion("us-east-1");
                      setSelectedTemplate("");
                    }}
                  >
                    <Cloud className="h-4 w-4 mr-2" />
                    AWS
                  </Button>
                  <Button
                    type="button"
                    variant={provider === "gcp" ? "default" : "outline"}
                    size="sm"
                    onClick={() => {
                      setProvider("gcp");
                      setRegion("us-central1");
                      setSelectedTemplate("");
                    }}
                  >
                    <Cloud className="h-4 w-4 mr-2" />
                    GCP
                  </Button>
                </div>
                <Badge variant="secondary" className="ml-auto">
                  {filteredTemplates.length} templates
                </Badge>
              </div>
              
              <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-3">
                {filteredTemplates.map((template) => (
                  <button
                    type="button"
                    key={template.id}
                    onClick={() => setSelectedTemplate(template.id)}
                    className={`rounded-lg border p-4 text-left transition ${
                      selectedTemplate === template.id ? "border-primary ring-2 ring-primary bg-primary/5" : "hover-elevate"
                    }`}
                  >
                    <div className="flex items-start justify-between mb-2">
                      <p className="text-lg font-semibold">{template.name}</p>
                      {selectedTemplate === template.id && (
                        <Badge variant="default" className="ml-2">Selected</Badge>
                      )}
                    </div>
                    <p className="text-sm text-muted-foreground mb-3">{template.description}</p>
                    <div className="flex flex-wrap gap-1.5">
                      {template.chips.slice(0, 3).map((chip) => (
                        <Badge key={chip} variant="secondary" className="text-xs">
                          {chip}
                        </Badge>
                      ))}
                      {template.chips.length > 3 && (
                        <Badge variant="outline" className="text-xs">
                          +{template.chips.length - 3}
                        </Badge>
                      )}
                    </div>
                  </button>
                ))}
              </div>
            </div>
          )}

          {step === 3 && (
            <div className="space-y-5">
              <h2 className="text-2xl font-semibold">Configure Provider</h2>
              <div className="grid gap-4 md:grid-cols-2">
                <button
                  type="button"
                  className={`rounded-lg border p-5 text-left transition ${provider === "aws" ? "border-primary ring-1 ring-primary" : "hover-elevate"}`}
                  onClick={() => {
                    setProvider("aws");
                    setRegion("us-east-1");
                  }}
                >
                  <Cloud className="mb-2 h-6 w-6 text-primary" />
                  <p className="text-3xl font-semibold">AWS</p>
                  <p className="text-muted-foreground">Amazon Web Services</p>
                </button>
                <button
                  type="button"
                  className={`rounded-lg border p-5 text-left transition ${provider === "gcp" ? "border-primary ring-1 ring-primary" : "hover-elevate"}`}
                  onClick={() => {
                    setProvider("gcp");
                    setRegion("us-central1");
                  }}
                >
                  <Cloud className="mb-2 h-6 w-6 text-primary" />
                  <p className="text-3xl font-semibold">GCP</p>
                  <p className="text-muted-foreground">Google Cloud Platform</p>
                </button>
              </div>

              <div>
                <Label className="mb-2 block">Region</Label>
                <Select value={region} onValueChange={setRegion}>
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent className="max-h-[300px]">
                    {regions.map((r) => (
                      <SelectItem key={r.code} value={r.code}>
                        {r.code} - {r.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <p className="mt-1 text-xs text-muted-foreground">
                  {regions.length} regions available for {provider.toUpperCase()}
                </p>
              </div>

              {/* Template Parameters - Only show for template method */}
              {method === "template" && selectedTemplateObj && selectedTemplateObj.parameters && selectedTemplateObj.parameters.length > 0 && (
                <div className="space-y-4 rounded-lg border p-4 bg-muted/30">
                  <h3 className="text-lg font-semibold">Template Parameters</h3>
                  <p className="text-sm text-muted-foreground">
                    Customize your {selectedTemplateObj.name} configuration
                  </p>
                  
                  <div className="grid gap-4 md:grid-cols-2">
                    {selectedTemplateObj.parameters.map((param) => (
                      <div key={param.name}>
                        <Label htmlFor={param.name} className="mb-2 block">
                          {param.label}
                          {param.required && <span className="text-destructive ml-1">*</span>}
                        </Label>
                        
                        {param.type === "select" && (
                          <Select
                            value={templateParams[param.name] || param.default?.toString()}
                            onValueChange={(value) => 
                              setTemplateParams({ ...templateParams, [param.name]: value })
                            }
                          >
                            <SelectTrigger id={param.name}>
                              <SelectValue />
                            </SelectTrigger>
                            <SelectContent className="max-h-[300px]">
                              {param.options?.map((opt) => (
                                <SelectItem key={opt.value} value={opt.value}>
                                  {opt.label}
                                </SelectItem>
                              ))}
                            </SelectContent>
                          </Select>
                        )}
                        
                        {param.type === "number" && (
                          <Input
                            type="number"
                            id={param.name}
                            value={templateParams[param.name] || param.default}
                            onChange={(e) => 
                              setTemplateParams({ ...templateParams, [param.name]: e.target.value })
                            }
                            min={param.min}
                            max={param.max}
                          />
                        )}
                        
                        {param.type === "text" && (
                          <Input
                            type="text"
                            id={param.name}
                            value={templateParams[param.name] || param.default}
                            onChange={(e) => 
                              setTemplateParams({ ...templateParams, [param.name]: e.target.value })
                            }
                          />
                        )}
                        
                        {param.description && (
                          <p className="mt-1 text-xs text-muted-foreground">{param.description}</p>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}

          {step === 4 && (
            <div className="space-y-4">
              <h2 className="text-2xl font-semibold">Review & Create</h2>
              <div className="grid gap-4 rounded-lg border p-4 md:grid-cols-2">
                <div>
                  <p className="text-sm text-muted-foreground">Method</p>
                  <p className="text-lg font-semibold">{method === "template" ? "Template" : "Natural Language"}</p>
                </div>
                <div>
                  <p className="text-sm text-muted-foreground">Provider</p>
                  <p className="text-lg font-semibold">{provider.toUpperCase()}</p>
                </div>
                <div>
                  <p className="text-sm text-muted-foreground">Region</p>
                  <p className="text-lg font-semibold">{region}</p>
                </div>
              </div>
              <div className="rounded-lg border p-4">
                <p className="text-sm text-muted-foreground">Infrastructure Request</p>
                <p className="mt-1 text-lg font-medium">
                  {method === "template"
                    ? `Template: ${selectedTemplateObj?.name ?? selectedTemplate}`
                    : request.trim()}
                </p>
              </div>
            </div>
          )}

          <div className="flex items-center justify-between">
            <Button variant="outline" disabled={step === 1} onClick={() => setStep((prev) => Math.max(1, prev - 1))}>
              <ArrowLeft className="mr-2 h-4 w-4" />
              Back
            </Button>
            {step < totalSteps ? (
              <Button disabled={!canNext} onClick={() => setStep((prev) => Math.min(totalSteps, prev + 1))}>
                Next
                <ArrowRight className="ml-2 h-4 w-4" />
              </Button>
            ) : (
              <Button onClick={() => createMutation.mutate()} disabled={!canNext || createMutation.isPending}>
                <Send className="mr-2 h-4 w-4" />
                {createMutation.isPending ? "Creating..." : "Create Run"}
              </Button>
            )}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
