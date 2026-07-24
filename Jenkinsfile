pipeline {
    agent any

    options {
        timestamps()
        disableConcurrentBuilds()
        timeout(time: 60, unit: 'MINUTES')
    }

    environment {
        IMAGE_NAME = 'manage-system'
        IMAGE_TAG = "${env.BUILD_NUMBER ?: 'local'}"
        PROJECT_CI = "manage-ci-${env.BUILD_NUMBER ?: 'local'}"
        COMPOSE_CI = 'docker-compose.ci.yml'
        COMPOSE_FULL = 'docker-compose.yml'
        PYTHONPATH = '.'
        FLASK_APP = 'app.main'
        DATABASE_URL = 'postgresql://postgres:ci_password@localhost:5432/inventory_db'
        E2E_BASE_URL = 'http://localhost:5000'
    }

    stages {
        stage('Checkout') {
            steps {
                checkout scm
            }
        }

        stage('Build') {
            steps {
                sh 'docker build -t ${IMAGE_NAME}:${IMAGE_TAG} .'
                sh '''
                    docker run --rm -v "$PWD:/app" -w /app python:3.12-slim \
                      bash -lc "pip install -q -r requirements.txt && python -c \"from app.main import app; assert app is not None\""
                '''
            }
        }

        stage('Tests') {
            parallel {
                stage('Unit tests') {
                    steps {
                        sh '''
                            docker run --rm -v "$PWD:/app" -w /app \
                              -e PYTHONPATH=/app python:3.12-slim \
                              bash -lc "pip install -q -r requirements.txt && pytest tests/test_products.py tests/test_stock.py -v --tb=short"
                        '''
                    }
                }

                stage('API / contract tests') {
                    steps {
                        sh '''
                            docker run --rm -v "$PWD:/app" -w /app \
                              -e PYTHONPATH=/app python:3.12-slim \
                              bash -lc "pip install -q -r requirements.txt && pytest tests/test_contract.py -v --tb=short"
                        '''
                    }
                }

                stage('Data / migration tests') {
                    steps {
                        sh '''
                            docker compose -f ${COMPOSE_CI} -p ${PROJECT_CI}-data up -d db
                            for i in $(seq 1 30); do
                              docker compose -f ${COMPOSE_CI} -p ${PROJECT_CI}-data exec -T db pg_isready -U postgres -d inventory_db && break
                              sleep 2
                            done
                            docker run --rm --network host -v "$PWD:/app" -w /app \
                              -e PYTHONPATH=/app -e FLASK_APP=app.main \
                              -e DATABASE_URL=${DATABASE_URL} \
                              python:3.12-slim \
                              bash -lc "pip install -q -r requirements.txt && flask db upgrade && pytest tests/data/ -v --tb=short"
                        '''
                    }
                    post {
                        always {
                            sh 'docker compose -f ${COMPOSE_CI} -p ${PROJECT_CI}-data down -v || true'
                        }
                    }
                }
            }
        }

        stage('Coverage') {
            steps {
                sh '''
                    docker compose -f ${COMPOSE_CI} -p ${PROJECT_CI}-cov up -d db
                    for i in $(seq 1 30); do
                      docker compose -f ${COMPOSE_CI} -p ${PROJECT_CI}-cov exec -T db pg_isready -U postgres -d inventory_db && break
                      sleep 2
                    done
                    docker run --rm --network host -v "$PWD:/app" -w /app \
                      -e PYTHONPATH=/app -e FLASK_APP=app.main \
                      -e DATABASE_URL=${DATABASE_URL} \
                      python:3.12-slim \
                      bash -lc "pip install -q -r requirements.txt && flask db upgrade && pytest tests/ -m 'not e2e' --cov=app --cov-report=xml --cov-report=term-missing --tb=short"
                '''
            }
            post {
                always {
                    junit allowEmptyResults: true, testResults: '**/report.xml'
                    sh 'docker compose -f ${COMPOSE_CI} -p ${PROJECT_CI}-cov down -v || true'
                }
            }
        }

        stage('Security') {
            steps {
                sh '''
                    docker run --rm -v "$PWD:/app" -w /app python:3.12-slim \
                      bash -lc "pip install -q pip-audit && pip-audit -r requirements.txt"
                '''
            }
        }

        stage('E2E') {
            steps {
                sh '''
                    docker compose -f ${COMPOSE_CI} -p ${PROJECT_CI} up -d --build
                    bash scripts/wait-for-services.sh \
                      "Flask" "http://localhost:5000/auth/login-page" \
                      "Keycloak" "http://localhost:8080/realms/inventory-realm/.well-known/openid-configuration"
                    docker compose -f ${COMPOSE_CI} -p ${PROJECT_CI} exec -T web flask db upgrade
                    COMPOSE_FILE=${COMPOSE_CI} COMPOSE_PROJECT=${PROJECT_CI} bash scripts/prepare-keycloak-e2e.sh
                    docker run --rm --network host \
                      -v "$PWD:/app" -w /app \
                      -e PYTHONPATH=/app \
                      -e E2E_BASE_URL=${E2E_BASE_URL} \
                      -e E2E_ALICE_USER=alice_worker \
                      -e E2E_ALICE_PASSWORD=password123 \
                      -e E2E_MANAGER_USER=kratos_boss \
                      -e E2E_MANAGER_PASSWORD=password123 \
                      mcr.microsoft.com/playwright/python:v1.60.0-jammy \
                      bash -lc "pip install -q -r requirements.txt && pytest tests/e2e -m e2e -v --tb=short"
                '''
            }
            post {
                always {
                    sh 'docker compose -f ${COMPOSE_CI} -p ${PROJECT_CI} down -v || true'
                }
            }
        }

        stage('Full stack + k6 smoke') {
            steps {
                sh '''
                    docker compose -f ${COMPOSE_FULL} down -v --remove-orphans || true
                    docker compose -f ${COMPOSE_FULL} up -d --build
                    bash scripts/wait-for-services.sh
                    docker compose -f ${COMPOSE_FULL} exec -T web flask db upgrade
                    COMPOSE_FILE=${COMPOSE_FULL} bash scripts/prepare-keycloak-e2e.sh
                    bash scripts/verify-stack.sh
                    mkdir -p reports
                    docker run --rm --network host \
                      -v "$PWD:/app" -w /app \
                      -e BASE_URL=http://localhost:5000 \
                      -e KEYCLOAK_URL=http://localhost:8080 \
                      grafana/k6:0.53.0 run tests/k6/smoke-test.js
                '''
            }
            post {
                always {
                    sh 'docker compose -f ${COMPOSE_FULL} down -v --remove-orphans || true'
                }
            }
        }

        stage('Docker image') {
            steps {
                sh 'docker build -t ${IMAGE_NAME}:ci .'
            }
        }
    }

    post {
        always {
            sh '''
                docker compose -f ${COMPOSE_CI} -p ${PROJECT_CI} down -v || true
                docker compose -f ${COMPOSE_CI} -p ${PROJECT_CI}-data down -v || true
                docker compose -f ${COMPOSE_CI} -p ${PROJECT_CI}-cov down -v || true
                docker compose -f ${COMPOSE_FULL} down -v --remove-orphans || true
            '''
            cleanWs()
        }
    }
}
