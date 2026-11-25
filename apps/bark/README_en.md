## Introduction

**Bark** is the self-hosted push server for the Bark iOS app. Send custom notifications to your iPhone through HTTP requests.

## Features

- **Custom notifications**: Send notifications using HTTP GET, POST, or JSON requests.
- **Storage**: Uses local Bbolt storage by default, with optional external MySQL support.
- **Authentication**: Supports optional HTTP Basic Auth; upstream exempts health checks and device registration from authentication.
