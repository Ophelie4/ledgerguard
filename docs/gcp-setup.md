# Google Cloud setup (one time)

These commands set up keyless deploys from GitLab CI to Cloud Run. Run them in Cloud Shell,
replacing `PROJECT_PATH` with the GitLab project path, for example `my-group/ledgerguard`.

```bash
PROJECT_ID=ledgerguard-2026ob
PROJECT_NUMBER=$(gcloud projects describe $PROJECT_ID --format='value(projectNumber)')
PROJECT_PATH=my-group/ledgerguard
SA=ledgerguard-deployer@$PROJECT_ID.iam.gserviceaccount.com

gcloud config set project $PROJECT_ID
gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com \
  iam.googleapis.com iamcredentials.googleapis.com sts.googleapis.com

# 1. Workload Identity pool + GitLab OIDC provider, restricted to ONE GitLab project
gcloud iam workload-identity-pools create gitlab-pool --location=global --display-name="GitLab"
gcloud iam workload-identity-pools providers create-oidc gitlab-provider \
  --location=global --workload-identity-pool=gitlab-pool \
  --issuer-uri="https://gitlab.com" \
  --allowed-audiences="https://iam.googleapis.com/projects/$PROJECT_NUMBER/locations/global/workloadIdentityPools/gitlab-pool/providers/gitlab-provider" \
  --attribute-mapping="google.subject=assertion.sub,attribute.project_path=assertion.project_path,attribute.ref=assertion.ref" \
  --attribute-condition="assertion.project_path=='$PROJECT_PATH' && assertion.ref=='main'"

# 2. Deployer service account with only what a Cloud Run source deploy needs
gcloud iam service-accounts create ledgerguard-deployer --display-name="LedgerGuard CI deployer"
for ROLE in roles/run.admin roles/cloudbuild.builds.editor roles/artifactregistry.admin \
            roles/storage.admin roles/serviceusage.serviceUsageConsumer roles/logging.viewer; do
  gcloud projects add-iam-policy-binding $PROJECT_ID --member="serviceAccount:$SA" --role=$ROLE --condition=None -q >/dev/null
done
# Cloud Run services run as the default compute service account; the deployer may act as it
gcloud iam service-accounts add-iam-policy-binding \
  $PROJECT_NUMBER-compute@developer.gserviceaccount.com \
  --member="serviceAccount:$SA" --role=roles/iam.serviceAccountUser
# Cloud Build (source deploys) runs as the default compute service account too
for ROLE in roles/cloudbuild.builds.builder roles/run.builder; do
  gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:$PROJECT_NUMBER-compute@developer.gserviceaccount.com" --role=$ROLE --condition=None -q >/dev/null
done

# 3. Let pipelines on main of that GitLab project impersonate the deployer
gcloud iam service-accounts add-iam-policy-binding $SA \
  --role=roles/iam.workloadIdentityUser \
  --member="principalSet://iam.googleapis.com/projects/$PROJECT_NUMBER/locations/global/workloadIdentityPools/gitlab-pool/attribute.project_path/$PROJECT_PATH"
```

Only pipelines on `main` of that one GitLab project can deploy. Merge request pipelines
never receive Google Cloud credentials.
